"""Shared "fetch or 404" lookups used across multiple routers."""

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import models


def get_ad_angle_request_or_404(db: Session, item_id: int) -> models.AdAngleRequest:
    row = db.query(models.AdAngleRequest).filter(models.AdAngleRequest.id == item_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Not found")
    return row


def get_angle_or_404(db: Session, angle_id: int) -> models.AdAngle:
    angle = db.query(models.AdAngle).filter(models.AdAngle.id == angle_id).first()
    if angle is None:
        raise HTTPException(status_code=404, detail="Angle not found")
    return angle


def get_angle_image_or_404(db: Session, image_id: int) -> models.AngleImage:
    image = db.query(models.AngleImage).filter(models.AngleImage.id == image_id).first()
    if image is None:
        raise HTTPException(status_code=404, detail="Image not found")
    return image


def get_logo_from_scratch_request_or_404(db: Session, request_id: int) -> models.LogoFromScratchRequest:
    row = (
        db.query(models.LogoFromScratchRequest)
        .filter(models.LogoFromScratchRequest.id == request_id)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Not found")
    return row


def get_logo_from_previous_request_or_404(db: Session, request_id: int) -> models.LogoFromPreviousRequest:
    row = (
        db.query(models.LogoFromPreviousRequest)
        .filter(models.LogoFromPreviousRequest.id == request_id)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Not found")
    return row


def get_logo_image_or_404(db: Session, image_id: int) -> models.LogoImage:
    image = db.query(models.LogoImage).filter(models.LogoImage.id == image_id).first()
    if image is None:
        raise HTTPException(status_code=404, detail="Logo image not found")
    return image


def get_post_generation_request_or_404(db: Session, item_id: int) -> models.PostGenerationRequest:
    row = (
        db.query(models.PostGenerationRequest)
        .filter(models.PostGenerationRequest.id == item_id)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Not found")
    return row


def get_post_or_404(db: Session, post_id: int) -> models.Post:
    row = db.query(models.Post).filter(models.Post.id == post_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Post not found")
    return row


def get_reel_or_404(db: Session, reel_id: int) -> models.Reel:
    row = db.query(models.Reel).filter(models.Reel.id == reel_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Reel not found")
    return row


def get_review_or_404(db: Session, review_id: int) -> models.Review:
    row = db.query(models.Review).filter(models.Review.id == review_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Review not found")
    return row


def get_post_image_or_404(db: Session, image_id: int) -> models.PostImage:
    image = db.query(models.PostImage).filter(models.PostImage.id == image_id).first()
    if image is None:
        raise HTTPException(status_code=404, detail="Image not found")
    return image


def get_reel_image_or_404(db: Session, image_id: int) -> models.ReelImage:
    image = db.query(models.ReelImage).filter(models.ReelImage.id == image_id).first()
    if image is None:
        raise HTTPException(status_code=404, detail="Image not found")
    return image


def get_website_content_request_or_404(db: Session, item_id: int) -> models.WebsiteContentRequest:
    row = (
        db.query(models.WebsiteContentRequest)
        .filter(models.WebsiteContentRequest.id == item_id)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Not found")
    return row


def get_website_section_or_404(db: Session, section_id: int) -> models.WebsiteSection:
    row = db.query(models.WebsiteSection).filter(models.WebsiteSection.id == section_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Section not found")
    return row


def get_blog_generation_request_or_404(db: Session, item_id: int) -> models.BlogGenerationRequest:
    row = (
        db.query(models.BlogGenerationRequest)
        .filter(models.BlogGenerationRequest.id == item_id)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Not found")
    return row


def get_blog_or_404(db: Session, blog_id: int) -> models.Blog:
    row = db.query(models.Blog).filter(models.Blog.id == blog_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Blog not found")
    return row
