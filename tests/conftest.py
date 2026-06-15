"""pytest 共享 Fixture — Django 初始化"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'zrag.settings')
django.setup()
