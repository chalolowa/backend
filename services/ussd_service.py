import json
from typing import Dict, Any, Optional
import inspect
from sqlalchemy import func
from sqlalchemy.orm import Session
from models.tenant import Tenant
from models.payment import Payment, PaymentStatus
from services.n8n_service import n8n_service
from core.config import REDIS_URL, REDIS_SESSION_TTL
import redis
import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Redis client (single connection pool shared across all USSDService instances)
# ---------------------------------------------------------------------------
try:
    redis_client = redis.from_url(
        REDIS_URL,
        decode_responses=True,   # always get str back, never bytes
        socket_connect_timeout=5,
        socket_timeout=5,
        retry_on_timeout=True,
    )
    redis_client.ping()
    logger.info("Redis Cloud connection established.")
except redis.RedisError as exc:
    logger.critical("Could not connect to Redis Cloud: %s", exc)
    raise


# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------
SESSION_PREFIX = "ussd:session:"


def _session_key(session_id: str) -> str:
    return f"{SESSION_PREFIX}{session_id}"


def _load_session(session_id: str, phone_number: str) -> Dict[str, Any]:
    """Load session from Redis; create a fresh one if it doesn't exist."""
    raw = redis_client.get(_session_key(session_id))
    if raw:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Corrupt session for %s — resetting.", session_id)

    return {"phone": phone_number, "step": "main_menu", "data": {}}


def _save_session(session_id: str, session: Dict[str, Any]) -> None:
    """Persist session to Redis with a rolling TTL."""
    redis_client.setex(
        _session_key(session_id),
        REDIS_SESSION_TTL,
        json.dumps(session),
    )


def _delete_session(session_id: str) -> None:
    """Remove session when the USSD dialogue ends."""
    redis_client.delete(_session_key(session_id))


# ---------------------------------------------------------------------------
# USSD Service
# ---------------------------------------------------------------------------
class USSDService:
    """
    Stateless USSD handler — all session state lives in Redis Cloud.

    Session schema:
        {
            "phone":  "+2547XXXXXXXX",
            "step":   "<current_step>",   # drives the state machine
            "data":   { ... }             # step-specific scratch space
        }
    """

    def __init__(self, db: Session):
        self.db = db

    def _get_tenant_by_phone(self, phone: str) -> Tenant | None:
        return (
            self.db.query(Tenant)
            .filter(Tenant.phone == phone)
            .filter(Tenant.is_active == True)
            .first()
        )

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------
    async def parse_ussd_input(
        self,
        text: str,
        session_id: str,
        phone_number: str,
        service_code: str,
    ) -> Dict[str, Any]:
        """Parse incoming USSD string and return the appropriate response.

        This method supports both sync and async step handlers. If the
        selected handler is a coroutine function it will be awaited.
        """

        session = _load_session(session_id, phone_number)

        # Africa's Talking sends the *full* input history as '*'-separated values.
        # The last segment is what the user typed at the current prompt.
        if text:
            inputs = text.split("*")
            current_input = inputs[-1] if inputs else ""
        else:
            current_input = ""
            session["step"] = "main_menu"   # fresh dial-in

        step = session["step"]

        dispatch = {
            "main_menu":       self._handle_main_menu,
            "view_balance":    self._handle_view_balance,
            "confirm_payment": self._handle_confirm_payment,
            "contact_menu":    self._handle_contact_menu,
            "report_issue":    self._handle_report_issue,
        }

        handler = dispatch.get(step)
        if handler:
            # call or await depending on handler type
            if inspect.iscoroutinefunction(handler):
                return await handler(user_input=current_input, session=session, session_id=session_id)
            else:
                return handler(user_input=current_input, session=session, session_id=session_id)

        # Unknown step — reset
        session["step"] = "main_menu"
        _save_session(session_id, session)
        return self._main_menu_response()

    # ------------------------------------------------------------------
    # Step handlers
    # ------------------------------------------------------------------
    def _handle_main_menu(
        self, user_input: str, session: Dict, session_id: str
    ) -> Dict[str, Any]:
        if not user_input:
            return self._main_menu_response()

        if user_input == "1":
            session["step"] = "view_balance"
            _save_session(session_id, session)
            return self._balance_inquiry_response(session)

        elif user_input == "2":
            session["step"] = "confirm_payment"
            session["data"]["confirm_step"] = "enter_amount"
            _save_session(session_id, session)
            return self._prompt_payment_amount()

        elif user_input == "3":
            session["step"] = "contact_menu"
            _save_session(session_id, session)
            return self._contact_menu_response()

        elif user_input == "0":
            _delete_session(session_id)
            return self._end_session_response("Thank you for using RentFlow. Goodbye.")

        else:
            return self._main_menu_response("Invalid choice. Please try again.")

    def _calculate_balance(self, tenant_id: int) -> float:
        tenant = self.db.query(Tenant).get(tenant_id)

        total_due = tenant.monthly_rent

        total_paid = (
            self.db.query(func.coalesce(func.sum(Payment.amount), 0))
            .filter(Payment.tenant_id == tenant_id)
            .filter(Payment.status == PaymentStatus.COMPLETED)
            .scalar()
        )

        return total_due - total_paid

    def _handle_view_balance(
        self, user_input: str, session: Dict, session_id: str
    ) -> Dict[str, Any]:
        """
        Fetch the tenant's balance.
        """
        balance = self._calculate_balance(session["tenant_id"])

        _delete_session(session_id)     # terminal step — clean up

        response = (
            f"END Your current rent balance is KES {balance}\n"
            f"Dial {session.get('service_code', '*117#')} for main menu"
        )
        return {"response": response, "session_id": session_id, "should_close": True}

    async def _handle_confirm_payment(
        self, user_input: str, session: Dict, session_id: str
    ) -> Dict[str, Any]:
        sub_step = session["data"].get("confirm_step", "enter_amount")

        if sub_step == "enter_amount":
            if not user_input or user_input == "0":
                session["step"] = "main_menu"
                _save_session(session_id, session)
                return self._main_menu_response()

            session["data"]["amount"] = user_input
            session["data"]["confirm_step"] = "enter_code"
            _save_session(session_id, session)
            return self._prompt_mpesa_code()

        elif sub_step == "enter_code":
            if not user_input or user_input == "0":
                session["step"] = "main_menu"
                _save_session(session_id, session)
                return self._main_menu_response()

            mpesa_code = user_input.strip().upper()
            amount = float(session["data"].get("amount", "0"))

            payment = Payment(
                tenant_id=session["tenant_id"],
                amount=amount,
                mpesa_code=mpesa_code,
                status=PaymentStatus.PENDING
            )

            self.db.add(payment)
            self.db.commit()

            try:
                await n8n_service.trigger_workflow("payment_confirmed", {
                    "phone": session["phone"],
                    "amount": amount,
                    "mpesa_code": mpesa_code,
                })
            except Exception as exc:
                logger.error("n8n trigger failed for payment_confirmed: %s", exc)

            _delete_session(session_id)

            response = (
                f"END Payment of KES {amount} confirmed.\n"
                f"M-Pesa code: {mpesa_code}\n"
                "Thank you for your payment!"
            )
            return {"response": response, "session_id": session_id, "should_close": True}

        return self._error_response(session_id)

    def _handle_contact_menu(
        self, user_input: str, session: Dict, session_id: str
    ) -> Dict[str, Any]:
        if not user_input:
            return self._contact_menu_response()

        categories = {
            "1": "Electrical/Meter problem",
            "2": "Water problem",
            "3": "Financial discrepancies",
            "4": "Garbage disposal",
            "5": "Other",
        }

        if user_input in categories:
            session["step"] = "report_issue"
            session["data"]["issue_category"] = categories[user_input]
            session["data"]["issue_step"] = "enter_description"
            _save_session(session_id, session)
            return self._prompt_issue_description()

        elif user_input == "0":
            session["step"] = "main_menu"
            _save_session(session_id, session)
            return self._main_menu_response()

        else:
            return self._contact_menu_response("Invalid choice. Please try again.")

    async def _handle_report_issue(
        self, user_input: str, session: Dict, session_id: str
    ) -> Dict[str, Any]:
        sub_step = session["data"].get("issue_step", "enter_description")

        if sub_step == "enter_description":
            if not user_input or user_input == "0":
                session["step"] = "main_menu"
                _save_session(session_id, session)
                return self._main_menu_response()

            # Truncate to 160 chars as advertised in the prompt
            description = user_input[:160]
            session["data"]["issue_description"] = description
            session["data"]["issue_step"] = "confirm"
            _save_session(session_id, session)

            response = (
                f"CON Issue: {session['data']['issue_category']}\n"
                f"Description: {description}\n\n"
                "1. Confirm\n"
                "2. Edit\n"
                "0. Cancel"
            )
            return {"response": response, "session_id": session_id, "should_close": False}

        elif sub_step == "confirm":
            if user_input == "1":
                try:
                    await n8n_service.trigger_workflow("issue_reported", {
                        "phone": session["phone"],
                        "category": session["data"]["issue_category"],
                        "description": session["data"]["issue_description"],
                    })
                except Exception as exc:
                    logger.error("n8n trigger failed for issue_reported: %s", exc)

                _delete_session(session_id)
                return {
                    "response": "END Your issue has been reported. The landlord will contact you soon.",
                    "session_id": session_id,
                    "should_close": True,
                }

            elif user_input == "2":           # BUG FIX: was `elif input == '2'`
                session["data"]["issue_step"] = "enter_description"
                _save_session(session_id, session)
                return self._prompt_issue_description()

            else:   # 0 or anything else → cancel
                session["step"] = "main_menu"
                _save_session(session_id, session)
                return self._main_menu_response()

        return self._error_response(session_id)

    # ------------------------------------------------------------------
    # Response builders
    # ------------------------------------------------------------------
    def _main_menu_response(self, error_msg: str = "") -> Dict[str, Any]:
        if error_msg:
            header = f"CON {error_msg}\n\n"
        else:
            header = "CON RentFlow Services\n"

        response = (
            header
            + "1. View Rent Balance\n"
            "2. Confirm Payment\n"
            "3. Contact Landlord\n"
            "0. Exit"
        )
        return {"response": response, "session_id": "", "should_close": False}

    def _balance_inquiry_response(self, session: Dict) -> Dict[str, Any]:
        response = "CON Please wait while we fetch your balance...\n0. Cancel"
        return {"response": response, "session_id": "", "should_close": False}

    def _prompt_payment_amount(self) -> Dict[str, Any]:
        response = "CON Enter the amount you want to pay:\n(e.g., 15000)\n0. Cancel"
        return {"response": response, "session_id": "", "should_close": False}

    def _prompt_mpesa_code(self) -> Dict[str, Any]:
        response = "CON Enter your M-Pesa transaction code:\n(e.g., QW12RT34)\n0. Cancel"
        return {"response": response, "session_id": "", "should_close": False}

    def _contact_menu_response(self, error_msg: str = "") -> Dict[str, Any]:
        header = f"CON {error_msg}\n\n" if error_msg else "CON Report an issue:\n"
        response = (
            header
            + "1. Electrical/Meter problem\n"
            "2. Water problem\n"
            "3. Financial discrepancies\n"
            "4. Garbage disposal\n"
            "5. Other\n"
            "0. Back to main menu"
        )
        return {"response": response, "session_id": "", "should_close": False}

    def _prompt_issue_description(self) -> Dict[str, Any]:
        response = "CON Briefly describe the issue:\n(max 160 characters)\n0. Cancel"
        return {"response": response, "session_id": "", "should_close": False}

    def _end_session_response(self, message: str) -> Dict[str, Any]:
        return {"response": f"END {message}", "session_id": "", "should_close": True}

    def _error_response(self, session_id: Optional[str] = None) -> Dict[str, Any]:
        if session_id:
            _delete_session(session_id)
        return {
            "response": "END An error occurred. Please try again.",
            "session_id": session_id or "",
            "should_close": True,
        }
