from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database import Base


class PostGenerationRequest(Base):
    """One month's content brief for one company.

    Two managers run off this row in parallel (see
    app.agents.post_generation.pipeline): the post manager writes `posts` AND
    `reels` from one model call, the review manager writes `reviews`. They fail
    independently, which is why there are two status columns rather than one.
    posts_status covers reels too, since a single call produces both.
    """

    __tablename__ = "post_generation_requests"

    id = Column(Integer, primary_key=True, index=True)
    company_name = Column(String, nullable=False)
    phone = Column(String, nullable=True)
    email = Column(String, nullable=True)
    website_url = Column(String, nullable=True)
    company_reviews_page_url = Column(String, nullable=True)
    month = Column(String, nullable=True)
    # Read by the image pipeline's headline/mood step, which derives a design
    # mood from the trade (Air Con gives "cool, crisp, refreshing").
    industry = Column(String, nullable=True)
    fixed_rules = Column(Text, nullable=True)
    main_topic = Column(Text, nullable=True)
    promotion = Column(Text, nullable=True)
    additional_resources = Column(Text, nullable=True)
    additional_notes = Column(Text, nullable=True)
    areas_covered = Column(Text, nullable=True)
    unique_selling_points = Column(Text, nullable=True)

    # JSON-encoded arrays/URLs of Supabase Storage public URLs — same convention
    # as AngleImage.company_image_paths.
    post_image_paths = Column(Text, nullable=True)
    logo_path = Column(String, nullable=True)
    # The review graphic is a template replication, so the client's template
    # image is the locked reference the generator copies.
    review_template_path = Column(String, nullable=True)

    # The researched hashtag pools, kept verbatim as the agents returned them.
    # Persisted so regenerating ONE post's hashtags later reuses the same pool
    # instead of paying for a fresh web search.
    post_hashtag_pool = Column(Text, nullable=True)
    review_hashtag_pool = Column(Text, nullable=True)
    # Raw Firecrawl output. Kept so a re-extraction can pick a different 8
    # reviews without scraping the page again, and so bad extractions are
    # debuggable after the fact.
    scraped_reviews_markdown = Column(Text, nullable=True)

    # pending | generating | complete | failed
    posts_status = Column(String, nullable=False, default="pending")
    reviews_status = Column(String, nullable=False, default="pending")
    # Hero-image generation + content-matching, a separate step from posts_status
    # (triggered by its own endpoint) since it runs its own image-generation calls
    # and a post/reel's content isn't required before its hero photo can be picked.
    images_status = Column(String, nullable=False, default="pending")
    # Whichever manager failed explains itself here. A dead reviews page is a
    # normal outcome to show the user, not a 500.
    error_message = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    posts = relationship(
        "Post",
        back_populates="request",
        order_by="Post.post_number",
        cascade="all, delete-orphan",
    )
    reels = relationship(
        "Reel",
        back_populates="request",
        order_by="Reel.reel_number",
        cascade="all, delete-orphan",
    )
    reviews = relationship(
        "Review",
        back_populates="request",
        order_by="Review.review_number",
        cascade="all, delete-orphan",
    )
    hero_images = relationship(
        "HeroImage",
        back_populates="request",
        order_by="HeroImage.slot",
        cascade="all, delete-orphan",
    )
