from django.shortcuts import redirect
from django.http import HttpResponseBadRequest, JsonResponse
from django.conf import settings
from google.oauth2.credentials import Credentials
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from googleapiclient.errors import HttpError
from googleapiclient.discovery import build

import json
import os

class GoogleCalendarInitView(View):
    def get(self, request, *args, **kwargs):
        flow = google_auth_oauthlib.flow.Flow.from_client_config(
            settings.GOOGLE_OAUTH2_CLIENT_CONFIG,
            scopes=settings.GOOGLE_OAUTH2_SCOPES,
            redirect_uri=request.build_absolute_uri(reverse('google-calendar-redirect')),
        )
        authorization_url, state = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
        )
        request.session['google_oauth2_state'] = state
        return redirect(authorization_url)


class GoogleCalendarRedirectView(View):
    def get(self, request, *args, **kwargs):
        if 'error' in request.GET:
            return HttpResponseBadRequest('Authorization error: {}'.format(request.GET['error']))

        if 'code' not in request.GET or 'state' not in request.GET:
            return HttpResponseBadRequest('Missing code or state parameter')

        if request.GET['state'] != request.session.get('google_oauth2_state'):
            return HttpResponseBadRequest('Invalid state parameter')

        flow = google_auth_oauthlib.flow.Flow.from_client_config(
            settings.GOOGLE_OAUTH2_CLIENT_CONFIG,
            scopes=settings.GOOGLE_OAUTH2_SCOPES,
            redirect_uri=request.build_absolute_uri(reverse('google-calendar-redirect')),
        )

        try:
            flow.fetch_token(authorization_response=request.build_absolute_uri(),
                             code=request.GET['code'])
        except FlowExchangeError as error:
            return HttpResponseBadRequest(str(error))

        credentials = flow.credentials
        request.session['google_oauth2_token'] = credentials_to_dict(credentials)
        return redirect(reverse('google-calendar-events'))


def credentials_to_dict(credentials):
    return {
        'token': credentials.token,
        'refresh_token': credentials.refresh_token,
        'token_uri': credentials.token_uri,
        'client_id': credentials.client_id,
        'client_secret': credentials.client_secret,
        'scopes': credentials.scopes
    }


def get_google_calendar_events(request):
    credentials = Credentials.from_authorized_user_info(info=request.session.get('google_oauth2_token'))

    try:
        service = build('calendar', 'v3', credentials=credentials)

        events_result = service.events().list(calendarId='primary', timeMin=datetime.datetime.utcnow().isoformat() + 'Z', maxResults=10, singleEvents=True, orderBy='startTime').execute()
        events = events_result.get('items', [])

        if not events:
            return JsonResponse({'status': 'error', 'message': 'No events found'})
        else:
            response_data = []
            for event in events:
                start = event['start'].get('dateTime', event['start'].get('date'))
                end = event['end'].get('dateTime', event['end'].get('date'))
                response_data.append({
                    'id': event['id'],
                    'summary': event['summary'],
                    'description': event.get('description', ''),
                    'location': event.get('location', ''),
                    'start': start,
                    'end': end,
                    'status': event['status']
                })
            return JsonResponse({'status': 'success', 'data': response_data})
    except HttpError as error:
        return JsonResponse({'status': 'error', 'message': 'An error occurred: {}'.
