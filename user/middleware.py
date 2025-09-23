from django.utils import translation

class UserLanguageMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            lang = request.user.language_code
            translation.activate(lang)
            request.LANGUAGE_CODE = lang
        response = self.get_response(request)

        if request.user.is_authenticated:
            response.setdefault('Content-Language', request.LANGUAGE_CODE)
        return response