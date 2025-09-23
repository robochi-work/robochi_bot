from .complete_user_work_profile_observer import UserWorkProfileCompleteObserver
from .publisher import WorkEventPublisher
from .events import WORK_PROFILE_COMPLETED


work_publisher = WorkEventPublisher()

work_publisher.subscribe(WORK_PROFILE_COMPLETED, UserWorkProfileCompleteObserver())



