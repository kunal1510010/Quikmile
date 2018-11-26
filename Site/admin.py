# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.contrib import admin

from .models import UserDetail, VehicleProfile, UserProfile

admin.site.register(UserDetail)
admin.site.register(VehicleProfile)
admin.site.register(UserProfile)