from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database import Base


class BlogGenerationRequest(Base):
    """One cluster brief for one client: the source of a batch of SEO blogs.

    Two phases run off this row, which is why there are two status columns rather
    than one (see app.services.blog_generation_service):

      metadata_status  scrape the homepage, structure it, and parse the pasted
                       Blog Schema into one Blog row per blog. Cheap, 3 calls.
      content_status   write, QC and revise every blog. Expensive: up to
                       MAX_QC_ROUNDS model calls per blog.

    Splitting them means a mis-parsed Blog Schema is caught for the price of the
    cheap phase, instead of after paying for a full run. The n8n workflow this
    came from went straight from the form to the writing, so a bad paste wasted
    everything.
    """

    __tablename__ = "blog_generation_requests"

    id = Column(Integer, primary_key=True, index=True)
    client_name = Column(String, nullable=False)
    website_url = Column(String, nullable=False)

    # The n8n form collected three themes, the first required. They are prompt
    # context for every blog in the cluster, not per-blog fields.
    cluster_theme_1 = Column(Text, nullable=False)
    cluster_theme_2 = Column(Text, nullable=True)
    cluster_theme_3 = Column(Text, nullable=True)

    # The form's "Cluster #". n8n collected this and then ignored it, hardcoding
    # 12 in two places instead. Here it is the expected blog count, checked
    # against what the extractor actually found.
    cluster_number = Column(Integer, nullable=True)

    # The pasted content plan, verbatim. Kept so a re-extraction can re-parse it
    # without the user pasting again, and so a bad parse is debuggable.
    blog_schema_raw = Column(Text, nullable=False)

    # Raw Firecrawl output for the homepage.
    scraped_markdown = Column(Text, nullable=True)
    # The structured markdown the website-content agent produced from it. Every
    # blog call injects this, so it is generated once and persisted rather than
    # re-derived per blog.
    website_content = Column(Text, nullable=True)

    # pending | extracting | complete | failed
    metadata_status = Column(String, nullable=False, default="pending")
    # pending | generating | complete | partial | failed
    #   complete -> every blog passed QC
    #   partial  -> the run finished but some blogs never reached the threshold
    content_status = Column(String, nullable=False, default="pending")
    error_message = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    blogs = relationship(
        "Blog",
        back_populates="request",
        order_by="Blog.blog_number",
        cascade="all, delete-orphan",
    )
