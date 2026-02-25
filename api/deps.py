from typing import Optional
from fastapi import Depends, HTTPException, status, Header
from sqlalchemy.orm import Session
from core.database import get_db
from models.landlord import Landlord

async def get_current_landlord(
        db: Session = Depends(get_db),
        x_landlord_id: Optional[int] = Header(None, alias="X-Landlord-Id")
):
    """
    Resolve the current landlord from a header provided by the frontend.

    Authentication is handled by the frontend; the frontend must pass
    the landlord's integer id in the `X-Landlord-Id` header on requests.
    """
    if x_landlord_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing X-Landlord-Id header")

    landlord = db.query(Landlord).filter(Landlord.id == x_landlord_id).first()
    if not landlord:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Landlord not found")

    return landlord