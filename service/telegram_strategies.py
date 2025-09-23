from abc import ABC, abstractmethod
from typing import Optional

from telebot import TeleBot
from telebot.types import LinkPreviewOptions, Message


class TelegramSendStrategy(ABC):
    default_link_preview_options = LinkPreviewOptions(is_disabled=True)
    default_reply_markup = None

    @abstractmethod
    def send(self, bot: TeleBot, chat_id: int, **kwargs) -> Message:
        ...

    @abstractmethod
    def update(self, bot: TeleBot, chat_id: int, message_id: int, **kwargs) -> Optional[Message]:
        ...


class TextStrategy(TelegramSendStrategy):
    def send(self, bot: TeleBot, chat_id: int, **kwargs) -> Message:
        return bot.send_message(
            chat_id=chat_id,
            text=kwargs['text'],
            reply_markup=kwargs.get('reply_markup', self.default_reply_markup),
            link_preview_options=kwargs.get('link_preview_options', self.default_link_preview_options),
        )

    def update(self, bot: TeleBot, chat_id: int, message_id: int, **kwargs) -> Optional[Message]:
        try:
            if kwargs.get('text'):
                return bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=kwargs['text'],
                    reply_markup=kwargs.get('reply_markup', self.default_reply_markup),
                    link_preview_options=kwargs.get('link_preview_options', self.default_link_preview_options),
                )
            elif kwargs.get('reply_markup'):
                return bot.edit_message_reply_markup(
                    chat_id=chat_id,
                    message_id=message_id,
                    reply_markup=kwargs.get('reply_markup', self.default_reply_markup),
                )
        except Exception as e:
            return None
        raise ValueError('kwargs must contain text or reply_markup')


class PhotoStrategy(TelegramSendStrategy):
    def send(self, bot: TeleBot, chat_id: int, **kwargs) -> Message:
        return bot.send_photo(
            chat_id=chat_id,
            photo=kwargs['photo'],
            caption=kwargs.get('caption', kwargs.get('text', '')),
            reply_markup=kwargs.get('reply_markup'),
        )

    def update(self, bot: TeleBot, chat_id: int, message_id: int, **kwargs) -> Optional[Message]:
        try:
            if kwargs.get('photo'):
                return bot.edit_message_caption(
                    chat_id=chat_id,
                    message_id=message_id,
                    caption=kwargs.get('caption', kwargs.get('text', '')),
                    reply_markup=kwargs.get('reply_markup'),
                )
            elif kwargs.get('reply_markup'):
                return bot.edit_message_reply_markup(
                    chat_id=chat_id,
                    message_id=message_id,
                    reply_markup=kwargs.get('reply_markup'),
                )
        except Exception as e:
            return None
        raise ValueError('kwargs must contain photo or reply_markup')

class InvoiceStrategy(TelegramSendStrategy):
    def send(self, bot: TeleBot, chat_id: int, **kwargs) -> Message:
        return bot.send_invoice(
            chat_id=chat_id,
            title=kwargs.get('title'),
            description=kwargs.get('description'),
            invoice_payload=kwargs.get('invoice_payload'),
            provider_token=kwargs.get('provider_token'),
            currency=kwargs.get('currency'),
            prices=kwargs.get('prices'),
            reply_markup=kwargs.get('reply_markup'),
            provider_data=kwargs.get('provider_data'),
        )

    def update(self, bot: TeleBot, chat_id: int, message_id: int, **kwargs) -> Optional[Message]:
        raise ValueError('Invoice strategy update method is not available')