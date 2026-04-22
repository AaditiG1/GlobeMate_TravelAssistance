
from app.models import Notification
from sqlalchemy.orm import Session

def add_notification(db: Session, user_id: int, title: str, message: str, n_type: str = "info"):
    new_notif = Notification(
        user_id=user_id,
        title=title,
        message=message,
        notif_type=n_type,
        is_read=False
    )
    db.add(new_notif)
    db.commit()