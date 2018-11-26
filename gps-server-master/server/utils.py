import logging
import math
import os
from asyncio import sleep

from aiohttp import ClientSession

GOOGLE_MAPS_API_KEY = os.environ.get('GOOGLE_MAPS_API_KEY', 'AIzaSyDBtJIStSH2RC-7822izRIOFCqMZeedVxY')
LOCATION_SERVICE_HOST = 'https://api.zonic.io/v1/location/'
logger = logging.getLogger(__name__)


class LocationServiceClient:
    def __init__(self):
        self._session = None

    async def set_session(self):
        if not self._session:
            self._session = ClientSession()
        return self._session

    async def reverse_geocode_api(self, lat, lng):
        await self.set_session()
        api = LOCATION_SERVICE_HOST + 'reverse-geocode/{lat}/{lng}/'.format(lat=lat, lng=lng)
        async with self._session.get(api) as r:
            if r.status == 200:
                result = await r.json()
                if isinstance(result, dict) and result.get('address'):
                    resp = result['address']
                    resp['id'] = result['id']
                    return resp

    async def create_geolocation(self, values):
        await self.set_session()
        api = LOCATION_SERVICE_HOST + 'geolocation/'
        async with self._session.post(api, json=values) as r:
            if r.status == 200:
                result = await r.json()
                return result


location_service = LocationServiceClient()


def rad2deg(radians):
    return radians * 57.295779513082323


def deg2rad(degrees):
    return degrees * 0.017453292519943295


def get_bearing(lat1, lon1, lat2, lon2):
    return (
                   rad2deg(
                       math.atan2(
                           math.sin(deg2rad(lon2) - deg2rad(lon1)) * math.cos(deg2rad(lat2)),
                           math.cos(deg2rad(lat1)) * math.sin(deg2rad(lat2)) - math.sin(deg2rad(lat1)) * math.cos(
                               deg2rad(lat2)) * math.cos(deg2rad(lon2) - deg2rad(lon1))
                       )
                   ) + 360
           ) % 360


def get_direction(bearing):
    direction = 'n'
    d = round(bearing / 22.5)
    if d == 1:
        direction = "nne"
    if d == 2:
        direction = "ne"
    if d == 3:
        direction = "ene"
    if d == 4:
        direction = "e"
    if d == 5:
        direction = "ese"
    if d == 6:
        direction = "se"
    if d == 7:
        direction = "sse"
    if d == 8:
        direction = "s"
    if d == 9:
        direction = "ssw"
    if d == 10:
        direction = "sw"
    if d == 11:
        direction = "wsw"
    if d == 12:
        direction = "w"
    if d == 13:
        direction = "wnw"
    if d == 14:
        direction = "nw"
    if d == 15:
        direction = "nnw"

    return direction


async def reversed_geocode_google_maps(lat, lng):
    api = "https://maps.googleapis.com/maps/api/geocode/json?latlng={lat},{lng}&key={api_key}"
    async with ClientSession() as session:
        async with session.get(api.format(lat=lat, lng=lng, api_key=GOOGLE_MAPS_API_KEY)) as r:
            if r.status == 200:
                result = await r.json()
                if result.get('error_message'):
                    return None
                return result


def gmaps_address_resolver(json):
    final = {}
    if json['results']:
        data = json['results'][0]
        for item in data['address_components']:
            for category in item['types']:
                data[category] = {}
                data[category] = item['long_name']
        final['locality'] = data.get("route", None)
        final['state'] = data.get("administrative_area_level_1", None)
        final['area'] = data.get("locality", None)
        final['city'] = data.get("administrative_area_level_2", None)
        final['country'] = data.get("country", None)
        final['postal_code'] = data.get("postal_code", None)
        final['neighborhood'] = data.get("neighborhood", None)
        final['sublocality'] = data.get("sublocality", None)
        final['housenumber'] = data.get("housenumber", None)
        final['postal_town'] = data.get("postal_town", None)
        final['subpremise'] = data.get("subpremise", None)
        final['latitude'] = data.get("geometry", {}).get("location", {}).get("lat", None)
        final['longitude'] = data.get("geometry", {}).get("location", {}).get("lng", None)
        final['location_type'] = data.get("geometry", {}).get("location_type", None)
        final['postal_code_suffix'] = data.get("postal_code_suffix", None)
        final['street_number'] = data.get('street_number', None)
        final['display_address'] = data.get('formatted_address', None)
    return final


async def reverse_geocode(lat, lng):
    address = await location_service.reverse_geocode_api(lat, lng)
    if address:
        address['source'] = 'Location Service'
        return address

    address_components = None
    result = await reversed_geocode_google_maps(lat, lng)
    if result:
        resolver = gmaps_address_resolver(result)
        address_components = {k: v for k, v in resolver.items() if v is not None}
        address_components['source'] = 'Google Maps'

    if address_components:
        values = dict()
        values['address'] = address_components
        values['lat'] = lat
        values['lng'] = lng
        geolocation = await location_service.create_geolocation(values)
        if geolocation:
            address_components['id'] = geolocation['id']
        logger.info("\nCreating Geolocation: \n{}".format(values))
    return address_components


async def call_later(func, period):
    try:
        await sleep(period)
        return await func
    except Exception as e:
        logger.error(str(e))
