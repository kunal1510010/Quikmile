# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models


class UserDetail(models.Model):
    user_id = models.AutoField(primary_key=True, null=False)
    user_name = models.CharField(max_length=20)
    email_id = models.EmailField()
    password = models.CharField(max_length=20)
    phone_number = models.IntegerField(null=True)
    address = models.CharField(null=True, max_length=100)
    vehicle_registered = models.BooleanField(default=False)
    def __str__(self):
        return str(self.user_id)


class VehicleProfile(models.Model):
    vehicle_id = models.AutoField(primary_key=True, null=False)
    imei_no = models.IntegerField(null=False)
    model_details = models.CharField(max_length=100)
    plate_number = models.CharField(max_length=20)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return str(self.vehicle_id)


class UserProfile(models.Model):
    user_id = models.ForeignKey(UserDetail)
    vehicle_id = models.ManyToManyField(VehicleProfile)

    def __str__(self):
        return  str(self.user_id)

