# -*- coding: utf-8 -*-
# Generated by Django 1.11.16 on 2018-10-23 18:20
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='UserDetail',
            fields=[
                ('user_id', models.AutoField(primary_key=True, serialize=False)),
                ('user_name', models.CharField(max_length=20)),
                ('email_id', models.EmailField(max_length=254)),
                ('password', models.CharField(max_length=20)),
                ('phone_number', models.IntegerField(null=True)),
                ('address', models.CharField(max_length=100, null=True)),
                ('vehicle_registered', models.BooleanField(default=False)),
            ],
        ),
        migrations.CreateModel(
            name='UserProfile',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('user_id', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='Site.UserDetail')),
            ],
        ),
        migrations.CreateModel(
            name='VehicleProfile',
            fields=[
                ('vehicle_id', models.AutoField(primary_key=True, serialize=False)),
                ('imei_no', models.IntegerField()),
                ('model_details', models.CharField(max_length=100)),
                ('plate_number', models.CharField(max_length=20)),
                ('is_active', models.BooleanField(default=True)),
            ],
        ),
        migrations.AddField(
            model_name='userprofile',
            name='vehicle_id',
            field=models.ManyToManyField(to='Site.VehicleProfile'),
        ),
    ]
