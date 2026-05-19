"""Google Calendar tools using Google Calendar API."""
import logging
from datetime import datetime, timedelta
from googleapiclient.discovery import build
from app.utils.google_auth import get_google_credentials
from app.tools.base import BaseTool, ToolSchema, ToolParameter

logger = logging.getLogger(__name__)


class GetCalendarEventsTool(BaseTool):
    """Get events from Google Calendar."""
    
    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="get_calendar_events",
            description="Get events from Google Calendar for a specified date range.",
            parameters=[
                ToolParameter(
                    name="days_ahead",
                    type="integer",
                    description="Number of days ahead to fetch events (default: 7)",
                    required=False
                ),
                ToolParameter(
                    name="max_results",
                    type="integer",
                    description="Maximum number of events to return (default: 10)",
                    required=False
                )
            ],
            return_type="string"
        )
    
    def execute(self, days_ahead: int = 7, max_results: int = 10, **kwargs) -> str:
        try:
            creds = get_google_credentials()
            service = build('calendar', 'v3', credentials=creds)
            
            # Calculate time range
            now = datetime.utcnow()
            time_min = now.isoformat() + 'Z'
            time_max = (now + timedelta(days=days_ahead)).isoformat() + 'Z'
            
            # Get events
            events_result = service.events().list(
                calendarId='primary',
                timeMin=time_min,
                timeMax=time_max,
                maxResults=max_results,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            events = events_result.get('items', [])
            
            if not events:
                return "No upcoming events found."
            
            result = f"Found {len(events)} upcoming events:\n\n"
            for event in events:
                start = event['start'].get('dateTime', event['start'].get('date'))
                end = event['end'].get('dateTime', event['end'].get('date'))
                title = event.get('summary', 'No title')
                location = event.get('location', 'No location')
                
                # Format datetime for display
                if 'T' in start:
                    start_dt = datetime.fromisoformat(start.replace('Z', '+00:00'))
                    start_str = start_dt.strftime('%Y-%m-%d %H:%M')
                else:
                    start_str = start
                
                result += f"📅 {title}\n"
                result += f"   Time: {start_str}\n"
                result += f"   Location: {location}\n"
                if 'description' in event:
                    result += f"   Description: {event['description'][:100]}...\n"
                result += "\n"
            
            logger.info(f"Retrieved {len(events)} calendar events")
            return result
            
        except Exception as e:
            logger.error(f"Failed to get calendar events: {str(e)}", exc_info=True)
            return f"Error getting calendar events: {str(e)}"


class CreateCalendarEventTool(BaseTool):
    """Create an event in Google Calendar."""
    
    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="create_calendar_event",
            description="Create a new event in Google Calendar.",
            parameters=[
                ToolParameter(
                    name="title",
                    type="string",
                    description="Event title",
                    required=True
                ),
                ToolParameter(
                    name="start_time",
                    type="string",
                    description="Start time in format 'YYYY-MM-DD HH:MM' or 'YYYY-MM-DD'",
                    required=True
                ),
                ToolParameter(
                    name="end_time",
                    type="string",
                    description="End time in format 'YYYY-MM-DD HH:MM' or 'YYYY-MM-DD'",
                    required=True
                ),
                ToolParameter(
                    name="description",
                    type="string",
                    description="Event description",
                    required=False
                ),
                ToolParameter(
                    name="location",
                    type="string",
                    description="Event location",
                    required=False
                )
            ],
            return_type="string"
        )
    
    def execute(self, title: str, start_time: str, end_time: str, description: str = None, location: str = None, **kwargs) -> str:
        try:
            creds = get_google_credentials()
            service = build('calendar', 'v3', credentials=creds)
            
            # Parse start and end times
            if len(start_time) == 10:  # Date only
                start_datetime = datetime.strptime(start_time, '%Y-%m-%d')
                start_iso = start_datetime.isoformat() + 'Z'
            else:  # Date and time
                start_datetime = datetime.strptime(start_time, '%Y-%m-%d %H:%M')
                start_iso = start_datetime.isoformat() + 'Z'
            
            if len(end_time) == 10:  # Date only
                end_datetime = datetime.strptime(end_time, '%Y-%m-%d')
                end_iso = end_datetime.isoformat() + 'Z'
            else:  # Date and time
                end_datetime = datetime.strptime(end_time, '%Y-%m-%d %H:%M')
                end_iso = end_datetime.isoformat() + 'Z'
            
            # Create event
            event = {
                'summary': title,
                'start': {
                    'dateTime': start_iso,
                    'timeZone': 'UTC',
                },
                'end': {
                    'dateTime': end_iso,
                    'timeZone': 'UTC',
                },
            }
            
            if description:
                event['description'] = description
            
            if location:
                event['location'] = location
            
            # Insert event
            event_result = service.events().insert(calendarId='primary', body=event).execute()
            
            logger.info(f"Created calendar event: {title}")
            return f"Event created successfully! Event ID: {event_result['id']}\nTitle: {title}\nStart: {start_time}\nEnd: {end_time}"
            
        except Exception as e:
            logger.error(f"Failed to create calendar event: {str(e)}", exc_info=True)
            return f"Error creating calendar event: {str(e)}"


class GetTodaysEventsTool(BaseTool):
    """Get today's events from Google Calendar."""
    
    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="get_todays_events",
            description="Get today's events from Google Calendar.",
            parameters=[
                ToolParameter(
                    name="max_results",
                    type="integer",
                    description="Maximum number of events to return (default: 20)",
                    required=False
                )
            ],
            return_type="string"
        )
    
    def execute(self, max_results: int = 20, **kwargs) -> str:
        try:
            creds = get_google_credentials()
            service = build('calendar', 'v3', credentials=creds)
            
            # Get today's date range
            now = datetime.utcnow()
            start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end_of_day = start_of_day + timedelta(days=1)
            
            time_min = start_of_day.isoformat() + 'Z'
            time_max = end_of_day.isoformat() + 'Z'
            
            # Get events
            events_result = service.events().list(
                calendarId='primary',
                timeMin=time_min,
                timeMax=time_max,
                maxResults=max_results,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            events = events_result.get('items', [])
            
            if not events:
                return "No events found for today."
            
            result = f"Found {len(events)} events for today:\n\n"
            for event in events:
                start = event['start'].get('dateTime', event['start'].get('date'))
                end = event['end'].get('dateTime', event['end'].get('date'))
                title = event.get('summary', 'No title')
                location = event.get('location', 'No location')
                
                # Format datetime for display
                if 'T' in start:
                    start_dt = datetime.fromisoformat(start.replace('Z', '+00:00'))
                    start_str = start_dt.strftime('%H:%M')
                else:
                    start_str = "All day"
                
                result += f"📅 {title}\n"
                result += f"   Time: {start_str}\n"
                result += f"   Location: {location}\n"
                if 'description' in event:
                    result += f"   Description: {event['description'][:100]}...\n"
                result += "\n"
            
            logger.info(f"Retrieved {len(events)} events for today")
            return result
            
        except Exception as e:
            logger.error(f"Failed to get today's events: {str(e)}", exc_info=True)
            return f"Error getting today's events: {str(e)}"
