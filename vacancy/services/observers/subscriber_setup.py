from service.notifications_impl import DjangoMessagesNotifier, TelegramNotifier
from telegram.handlers.bot_instance import bot

from .approved_channel_observer import VacancyApprovedChannelObserver
from .approved_group_observer import VacancyApprovedGroupObserver
from .approved_user_observer import VacancyApprovedUserObserver
from .auto_rating import AutoRatingObserver
from .call_observer import (
    VacancyAfterStartCallFailObserver,
    VacancyAfterStartCallObserver,
    VacancyAfterStartCallSuccessObserver,
    VacancyBeforeCallObserver,
    VacancyStartCallFailObserver,
    VacancyStartCallObserver,
)
from .created_admin_observer import VacancyCreatedAdminObserver
from .created_user_observer import VacancyCreatedUserDjangoObserver, VacancyCreatedUserObserver
from .events import (
    VACANCY_AFTER_START_CALL,
    VACANCY_AFTER_START_CALL_FAIL,
    VACANCY_AFTER_START_CALL_SUCCESS,
    VACANCY_APPROVED,
    VACANCY_BEFORE_CALL,
    VACANCY_CLOSE,
    VACANCY_CLOSE_FORCIBLY,
    VACANCY_CLOSE_PAYMENT_DOES_NOT_EXIST,
    VACANCY_CREATED,
    VACANCY_DELETE,
    VACANCY_LEFT_MEMBER,
    VACANCY_NEW_FEEDBACK,
    VACANCY_NEW_MEMBER,
    VACANCY_REFIND,
    VACANCY_REJECTED,
    VACANCY_START_CALL,
    VACANCY_START_CALL_FAIL,
)
from .feedback import VacancyFeedbackAdminObserver
from .member_observer import VacancyIsFullObserver, VacancySlotFreedObserver
from .publisher import VacancyEventPublisher
from .refind_observer import VacancyRefindAdminObserver, VacancyRefindChannelObserver
from .rejected_user_observer import VacancyRejectedUserObserver
from .renewal_observer import VacancyRenewalWorkersObserver
from .resend_channel_observer import VacancyTopResendChannelObserver
from .vacancy_close import (
    VacancyDeleteMessagesChannelObserver,
    VacancyDeleteMessagesObserver,
    VacancyGroupFeeStatusObserver,
    VacancyKickGroupUsersObserver,
    VacancyNotifyAdminsObserver,
    VacancyPaymentDoesNotExistObserver,
    VacancyStatusClosedObserver,
)

vacancy_publisher = VacancyEventPublisher()

telegram_notifier = TelegramNotifier(bot)
vacancy_publisher.subscribe(VACANCY_CREATED, VacancyCreatedUserObserver(telegram_notifier))
vacancy_publisher.subscribe(VACANCY_CREATED, VacancyCreatedAdminObserver(telegram_notifier))
vacancy_publisher.subscribe(VACANCY_APPROVED, VacancyApprovedUserObserver(telegram_notifier))
vacancy_publisher.subscribe(VACANCY_APPROVED, VacancyApprovedChannelObserver(telegram_notifier))
vacancy_publisher.subscribe(VACANCY_APPROVED, VacancyApprovedGroupObserver(telegram_notifier))
vacancy_publisher.subscribe(VACANCY_APPROVED, VacancyRenewalWorkersObserver(telegram_notifier))
vacancy_publisher.subscribe(VACANCY_REJECTED, VacancyRejectedUserObserver(telegram_notifier))

vacancy_publisher.subscribe(VACANCY_NEW_MEMBER, VacancyIsFullObserver(telegram_notifier))
vacancy_publisher.subscribe(VACANCY_NEW_MEMBER, VacancyTopResendChannelObserver(telegram_notifier))
vacancy_publisher.subscribe(VACANCY_LEFT_MEMBER, VacancySlotFreedObserver(telegram_notifier))
vacancy_publisher.subscribe(VACANCY_BEFORE_CALL, VacancyBeforeCallObserver(telegram_notifier))

vacancy_publisher.subscribe(VACANCY_REFIND, VacancyRefindChannelObserver(telegram_notifier))
vacancy_publisher.subscribe(VACANCY_REFIND, VacancyRefindAdminObserver(telegram_notifier))

vacancy_publisher.subscribe(VACANCY_START_CALL, VacancyStartCallObserver(telegram_notifier))
vacancy_publisher.subscribe(VACANCY_START_CALL_FAIL, VacancyStartCallFailObserver(telegram_notifier))
vacancy_publisher.subscribe(VACANCY_AFTER_START_CALL, VacancyAfterStartCallObserver(telegram_notifier))
vacancy_publisher.subscribe(VACANCY_AFTER_START_CALL_SUCCESS, VacancyAfterStartCallSuccessObserver(telegram_notifier))
vacancy_publisher.subscribe(VACANCY_AFTER_START_CALL_FAIL, VacancyAfterStartCallFailObserver(telegram_notifier))

vacancy_publisher.subscribe(VACANCY_NEW_FEEDBACK, VacancyFeedbackAdminObserver(telegram_notifier))

auto_rating_observer = AutoRatingObserver()
vacancy_publisher.subscribe(VACANCY_START_CALL_FAIL, auto_rating_observer)
vacancy_publisher.subscribe(VACANCY_AFTER_START_CALL_FAIL, auto_rating_observer)
vacancy_publisher.subscribe(VACANCY_AFTER_START_CALL_SUCCESS, auto_rating_observer)
vacancy_publisher.subscribe(VACANCY_CLOSE, auto_rating_observer)

vacancy_publisher.subscribe(VACANCY_CLOSE, VacancyStatusClosedObserver(telegram_notifier))
vacancy_publisher.subscribe(VACANCY_CLOSE, VacancyDeleteMessagesObserver(telegram_notifier))
vacancy_publisher.subscribe(VACANCY_CLOSE, VacancyKickGroupUsersObserver(telegram_notifier))
vacancy_publisher.subscribe(VACANCY_CLOSE, VacancyGroupFeeStatusObserver(telegram_notifier))
vacancy_publisher.subscribe(VACANCY_CLOSE, VacancyNotifyAdminsObserver(telegram_notifier))
vacancy_publisher.subscribe(VACANCY_CLOSE_PAYMENT_DOES_NOT_EXIST, VacancyPaymentDoesNotExistObserver(telegram_notifier))

vacancy_publisher.subscribe(VACANCY_CLOSE_FORCIBLY, VacancyDeleteMessagesChannelObserver(telegram_notifier))

vacancy_publisher.subscribe(VACANCY_DELETE, VacancyDeleteMessagesObserver(telegram_notifier))
vacancy_publisher.subscribe(VACANCY_DELETE, VacancyKickGroupUsersObserver(telegram_notifier))
vacancy_publisher.subscribe(VACANCY_DELETE, VacancyGroupFeeStatusObserver(telegram_notifier))
vacancy_publisher.subscribe(VACANCY_DELETE, VacancyDeleteMessagesChannelObserver(telegram_notifier))

django_notifier = DjangoMessagesNotifier()
vacancy_publisher.subscribe(VACANCY_CREATED, VacancyCreatedUserDjangoObserver(django_notifier))
