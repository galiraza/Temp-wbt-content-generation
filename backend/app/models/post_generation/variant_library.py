from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text, UniqueConstraint

from app.database import Base


class VariantLibrary(Base):
    """The design-layout library the final branded post/review images are
    built from - a global, shared table (every client/month picks from the
    same set), replacing the single Google Doc the n8n workflow read at
    generation time.

    The source doc turned out to hold TWO separate variant systems, not one
    flat set: post-image layouts (logo/headline/subheadline/CTA/hero photo)
    and review-image layouts (reviewer name/star rating/customer quote) are
    structurally different design languages, so `kind` distinguishes them -
    both reuse the letter scheme (A, B, C...) independently, which is why
    `letter` alone isn't unique.

    `layout_block` still carries the source doc's own {{PRIMARY_HEX}} /
    {{ACCENT_HEX}} / {{BG_HEX}} / {{NEUTRAL_HEX}} placeholders verbatim -
    substituted at generation time the same way as before
    (final_image_prompt.substitute_variant_colors), not here.
    """

    __tablename__ = "variant_library"

    id = Column(Integer, primary_key=True, index=True)
    kind = Column(String, nullable=False)  # "post" | "review"
    letter = Column(String(1), nullable=False)  # A-Z
    layout_block = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("kind", "letter", name="uq_variant_library_kind_letter"),
    )
