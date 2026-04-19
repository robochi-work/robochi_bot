from .complete_user_work_profile_observer import UserWorkProfileCompleteObserver
from .events import WORK_PROFILE_COMPLETED
from .publisher import WorkEventPublisher

work_publisher = WorkEventPublisher()

work_publisher.subscribe(WORK_PROFILE_COMPLETED, UserWorkProfileCompleteObserver())
