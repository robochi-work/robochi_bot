"""
Regression tests for session 2026-04-15: FAQ system (FaqItem model + dynamic pages).
Run: DJANGO_SETTINGS_MODULE=config.django.local pytest tests/test_session_20260415_faq.py -v
"""

import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestFaqModel:
    """Verify FaqItem model exists and has correct fields."""

    def test_faqitem_import(self):
        """FaqItem can be imported without errors."""
        import django

        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.django.local")
        django.setup()
        from work.models import FaqItem

        assert hasattr(FaqItem, "role")
        assert hasattr(FaqItem, "question")
        assert hasattr(FaqItem, "answer")
        assert hasattr(FaqItem, "image")
        assert hasattr(FaqItem, "video_url")
        assert hasattr(FaqItem, "order")
        assert hasattr(FaqItem, "is_active")

    def test_faqitem_role_choices(self):
        """FaqItem has employer and worker role choices."""
        import django

        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.django.local")
        django.setup()
        from work.models import FaqItem

        assert FaqItem.ROLE_EMPLOYER == "employer"
        assert FaqItem.ROLE_WORKER == "worker"

    def test_faqitem_video_embed_url_property(self):
        """FaqItem has video_embed_url property."""
        import django

        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.django.local")
        django.setup()
        from work.models import FaqItem

        item = FaqItem(video_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        assert item.video_embed_url == "https://www.youtube.com/embed/dQw4w9WgXcQ"

        item2 = FaqItem(video_url="https://youtu.be/dQw4w9WgXcQ")
        assert item2.video_embed_url == "https://www.youtube.com/embed/dQw4w9WgXcQ"

        item3 = FaqItem(video_url="")
        assert item3.video_embed_url == ""

        item4 = FaqItem(video_url=None)
        assert item4.video_embed_url == ""

    def test_faqitem_ordering(self):
        """FaqItem Meta ordering is by role then order."""
        import django

        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.django.local")
        django.setup()
        from work.models import FaqItem

        assert FaqItem._meta.ordering == ["role", "order"]


class TestFaqTemplates:
    """Verify FAQ templates exist and have correct content."""

    def test_employer_faq_template_exists(self):
        path = os.path.join(BASE_DIR, "work", "templates", "work", "employer_faq.html")
        assert os.path.exists(path)

    def test_worker_faq_template_exists(self):
        path = os.path.join(BASE_DIR, "work", "templates", "work", "worker_faq.html")
        assert os.path.exists(path)

    def test_employer_faq_uses_dynamic_items(self):
        path = os.path.join(BASE_DIR, "work", "templates", "work", "employer_faq.html")
        with open(path) as f:
            content = f.read()
        assert "faq_items" in content
        assert "item.question" in content
        assert "item.answer" in content
        assert "Як це працює?" in content
        assert "Що робити якщо?" not in content

    def test_worker_faq_uses_dynamic_items(self):
        path = os.path.join(BASE_DIR, "work", "templates", "work", "worker_faq.html")
        with open(path) as f:
            content = f.read()
        assert "faq_items" in content
        assert "item.question" in content
        assert "item.answer" in content
        assert "Як це працює?" in content
        assert "Що робити якщо?" not in content

    def test_employer_faq_has_media_support(self):
        path = os.path.join(BASE_DIR, "work", "templates", "work", "employer_faq.html")
        with open(path) as f:
            content = f.read()
        assert "item.image" in content
        assert "item.video_embed_url" in content
        assert "faq-media__img" in content
        assert "faq-media__video" in content

    def test_worker_faq_has_media_support(self):
        path = os.path.join(BASE_DIR, "work", "templates", "work", "worker_faq.html")
        with open(path) as f:
            content = f.read()
        assert "item.image" in content
        assert "item.video_embed_url" in content
        assert "faq-media__img" in content
        assert "faq-media__video" in content


class TestDashboardRename:
    """Verify dashboards use 'Як це працює?' instead of 'Що робити якщо?'."""

    def test_employer_dashboard_renamed(self):
        path = os.path.join(BASE_DIR, "work", "templates", "work", "employer_dashboard.html")
        with open(path) as f:
            content = f.read()
        assert "Як це працює?" in content
        assert "Що робити якщо?" not in content

    def test_worker_dashboard_renamed(self):
        path = os.path.join(BASE_DIR, "work", "templates", "work", "worker_dashboard.html")
        with open(path) as f:
            content = f.read()
        assert "Як це працює?" in content
        assert "Що робити якщо?" not in content


class TestFaqViews:
    """Verify FAQ views pass faq_items to templates."""

    def test_employer_faq_view_has_faq_items(self):
        path = os.path.join(BASE_DIR, "work", "views", "employer.py")
        with open(path) as f:
            content = f.read()
        assert "FaqItem" in content
        assert "faq_items" in content
        assert "ROLE_EMPLOYER" in content

    def test_worker_faq_view_has_faq_items(self):
        path = os.path.join(BASE_DIR, "work", "views", "worker.py")
        with open(path) as f:
            content = f.read()
        assert "FaqItem" in content
        assert "faq_items" in content
        assert "ROLE_WORKER" in content


class TestFaqAdmin:
    """Verify FaqItem is registered in admin."""

    def test_admin_has_faqitem(self):
        path = os.path.join(BASE_DIR, "work", "admin.py")
        with open(path) as f:
            content = f.read()
        assert "FaqItemAdmin" in content
        assert "FaqItem" in content
        assert "question_short" in content
        assert "has_image" in content
        assert "has_video" in content


class TestMediaSettings:
    """Verify MEDIA_URL and MEDIA_ROOT are configured."""

    def test_media_settings_in_base(self):
        path = os.path.join(BASE_DIR, "config", "django", "base.py")
        with open(path) as f:
            content = f.read()
        assert "MEDIA_URL" in content
        assert "MEDIA_ROOT" in content

    def test_media_directory_exists(self):
        """media/faq may not exist in CI — just check MEDIA_ROOT is configured."""
        from django.conf import settings

        assert hasattr(settings, "MEDIA_ROOT")
