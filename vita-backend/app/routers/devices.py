import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user, get_device_from_api_key
from app.database import get_db
from app.models.device import Device
from app.models.user import User
from app.schemas.device import DeviceOut, DeviceRegister

router = APIRouter(prefix="/devices", tags=["devices"])


@router.post("/register", response_model=DeviceOut, status_code=status.HTTP_201_CREATED)
def register_device(
    body: DeviceRegister,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    existing = db.query(Device).filter(Device.device_uid == body.device_uid).first()
    if existing:
        if existing.user_id != current_user.id:
            raise HTTPException(status_code=400, detail="Device already registered to another account")
        # Re-register: update name/type and reactivate
        existing.device_name = body.device_name
        existing.device_type = body.device_type
        existing.is_active = True
        db.commit()
        db.refresh(existing)
        return existing

    device = Device(
        user_id=current_user.id,
        device_uid=body.device_uid,
        device_name=body.device_name,
        device_type=body.device_type,
        api_key=secrets.token_hex(32),
    )
    db.add(device)
    db.commit()
    db.refresh(device)
    return device


@router.get("/", response_model=list[DeviceOut])
def list_devices(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return db.query(Device).filter(Device.user_id == current_user.id).all()


@router.get("/status")
def device_status(
    device: Device = Depends(get_device_from_api_key),
):
    """ESP32 calls this (no JWT needed) to confirm its API key is valid.
    Returns 200 + device info if registered, 401 if not found / inactive."""
    return {
        "ok": True,
        "device_name": device.device_name,
        "device_type": device.device_type,
    }


@router.delete("/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_device(
    device_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Permanently deletes the device. Associated vitals records are kept (device_id set to NULL)."""
    device = db.query(Device).filter(
        Device.id == device_id, Device.user_id == current_user.id
    ).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    db.delete(device)
    db.commit()
