# -*- coding: utf-8 -*-
# Generated by Django 1.9.7 on 2018-03-25 03:37
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('gitos', '0004_githubissuebounty'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='githubissuebounty',
            name='currency',
        ),
    ]
