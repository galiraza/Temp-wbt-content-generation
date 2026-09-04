import json
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.routers.dependencies import get_ad_angle_request_or_404
from app.services.ad_angle_service import generate_angles_for_request, to_out
from app.storage import delete_file

router = APIRouter(prefix="/api/ad-angles", tags=["ad-angles"])


@router.post("", response_model=schemas.AdAngleRequestOut)
def create_ad_angle_request(payload: schemas.AdAngleRequestCreate, db: Session = Depends(get_db)):
    row = models.AdAngleRequest(
        company_name=payload.company_name,
        offers=json.dumps(payload.offers),
        service_name=payload.service_name,
        service_content=payload.service_content,
        industry=json.dumps(payload.industry),
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    generated = generate_angles_for_request(row)
    for i, (headline, primary_text) in enumerate(generated):
        db.add(
            models.AdAngle(
                request_id=row.id, headline=headline, primary_text=primary_text, order=i
            )
        )
    db.commit()

    return to_out(row)


@router.get("", response_model=List[schemas.AdAngleRequestOut])
def list_ad_angle_requests(db: Session = Depends(get_db)):
    rows = db.query(models.AdAngleRequest).order_by(models.AdAngleRequest.id.desc()).all()
    return [to_out(r) for r in rows]


@router.get("/{item_id}", response_model=schemas.AdAngleRequestOut)
def get_ad_angle_request(item_id: int, db: Session = Depends(get_db)):
    return to_out(get_ad_angle_request_or_404(db, item_id))


@router.put("/{item_id}", response_model=schemas.AdAngleRequestOut)
def update_ad_angle_request(
    item_id: int, payload: schemas.AdAngleRequestUpdate, db: Session = Depends(get_db)
):
    row = get_ad_angle_request_or_404(db, item_id)

    data = payload.model_dump(exclude_unset=True)
    if "offers" in data:
        data["offers"] = json.dumps(data["offers"])
    if "industry" in data:
        data["industry"] = json.dumps(data["industry"])
    for key, value in data.items():
        setattr(row, key, value)

    db.commit()
    db.refresh(row)
    return to_out(row)


@router.post("/{item_id}/regenerate", response_model=List[schemas.AngleOut])
def regenerate_all_angles(
    item_id: int,
    payload: Optional[schemas.AdAngleRequestUpdate] = None,
    db: Session = Depends(get_db),
):
    """Regenerate all angles for a request, updating existing angle rows in place.

    Optionally accepts updated request fields (company name, offers, service
    name/content, industry) so the "Run again" flow can edit the brief and
    regenerate in a single call.

    Existing AdAngle rows are updated in place (headline/primary_text/status
    reset to "pending") rather than deleted and recreated. This preserves each
    angle's id, so its generated images (and their files) are left untouched —
    a delete+recreate previously cascaded into deleting every image for the
    request, even though the user only asked to regenerate the angle copy.

    If the newly generated count differs from the existing count, surplus
    existing rows are removed (and their images' files cleaned up) and/or new
    rows are added, but only for the rows actually beyond the overlap.

    The slow AI call (~80s) runs BEFORE any existing rows are touched, and the
    row updates happen only right before the final commit — keeping the
    mutation window down to milliseconds instead of ~80 seconds.
    """
    row = get_ad_angle_request_or_404(db, item_id)

    if payload is not None:
        data = payload.model_dump(exclude_unset=True)
        if "offers" in data:
            data["offers"] = json.dumps(data["offers"])
        if "industry" in data:
            data["industry"] = json.dumps(data["industry"])
        for key, value in data.items():
            setattr(row, key, value)

    generated = generate_angles_for_request(row)

    existing_angles = (
        db.query(models.AdAngle)
        .filter(models.AdAngle.request_id == row.id)
        .order_by(models.AdAngle.order)
        .all()
    )

    angles = []
    for i, (headline, primary_text) in enumerate(generated):
        if i < len(existing_angles):
            angle = existing_angles[i]
            angle.headline = headline
            angle.primary_text = primary_text
            angle.status = "pending"
            angle.order = i
        else:
            angle = models.AdAngle(
                request_id=row.id, headline=headline, primary_text=primary_text, order=i
            )
            db.add(angle)
        angles.append(angle)

    for angle in existing_angles[len(generated) :]:
        for image in angle.images:
            delete_file(image.file_path)
        db.delete(angle)

    db.commit()
    for angle in angles:
        db.refresh(angle)
    return angles


@router.delete("/{item_id}", status_code=204)
def delete_ad_angle_request(item_id: int, db: Session = Depends(get_db)):
    row = get_ad_angle_request_or_404(db, item_id)
    db.delete(row)
    db.commit()
    return None


@router.get("/{item_id}/angles", response_model=List[schemas.AngleOut])
def list_angles(item_id: int, db: Session = Depends(get_db)):
    get_ad_angle_request_or_404(db, item_id)
    return (
        db.query(models.AdAngle)
        .filter(models.AdAngle.request_id == item_id)
        .order_by(models.AdAngle.order)
        .all()
    )
