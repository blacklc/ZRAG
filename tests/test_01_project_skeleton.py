"""Tracer Bullet: Django 项目骨架正确初始化"""
from django.core.management import call_command


class TestProjectSkeleton:
    """切片 1 — 项目骨架"""

    def test_django_check_passes(self):
        """Django 项目检查通过：manage.py check 不报错"""
        call_command('check')
