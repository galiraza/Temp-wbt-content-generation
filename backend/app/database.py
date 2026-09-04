from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import DATABASE_URL

# pool_pre_ping: Supabase fronts Postgres with a pooler that closes idle
# connections, and several endpoints hold a Session open across many minutes of
# external API calls -- hero-image generation, and a website-content run sitting
# between commits while a model writes a page. The pooler drops the connection
# underneath it, and the next query dies with "server closed the connection
# unexpectedly": a raw 503 that abandons the run mid-flight. Hit independently
# on both the image and website-content paths. pre_ping spends one round trip
# checking a pooled connection is alive before handing it out, and reconnects
# transparently if it is not.
#
# pool_recycle is the belt to that braces: any connection older than this is
# discarded rather than reused, so one the pooler is about to drop is usually
# retired by us first. Well under Supabase's own idle timeout.
engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=1800)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
