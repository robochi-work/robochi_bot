from django.shortcuts import render
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required


def phone_required_view(request):
    """Page shown when user opens WebApp without confirming phone number."""
    return render(request, 'work/phone_required.html')


@login_required
def resend_phone_request(request):
    """API endpoint: resend phone request button to user's bot chat."""
    from telegram.handlers.bot_instance import get_bot
    from telebot import types

    user = request.user
    bot = get_bot()
    try:
        markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
        markup.add(types.KeyboardButton('Надіслати номер телефону', request_contact=True))
        bot.send_message(
            user.telegram_id or user.id,
            'Для продовження надішліть ваш номер телефону:',
            reply_markup=markup,
        )
        return JsonResponse({"ok": True})
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=500)
