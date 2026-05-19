"""Gmail tools using Gmail API."""
import logging
import base64
import email
from datetime import datetime, timedelta
from googleapiclient.discovery import build
from app.utils.google_auth import get_google_credentials
from app.tools.base import BaseTool, ToolSchema, ToolParameter

logger = logging.getLogger(__name__)


class GetEmailsTool(BaseTool):
    """Get emails from Gmail."""
    
    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="get_emails",
            description="Get emails from Gmail inbox.",
            parameters=[
                ToolParameter(
                    name="max_results",
                    type="integer",
                    description="Maximum number of emails to return (default: 10)",
                    required=False
                ),
                ToolParameter(
                    name="query",
                    type="string",
                    description="Gmail search query (e.g., 'from:john@example.com', 'subject:meeting')",
                    required=False
                ),
                ToolParameter(
                    name="unread_only",
                    type="boolean",
                    description="Get only unread emails (default: false)",
                    required=False
                )
            ],
            return_type="string"
        )
    
    def execute(self, max_results: int = 10, query: str = None, unread_only: bool = False, **kwargs) -> str:
        try:
            creds = get_google_credentials()
            service = build('gmail', 'v1', credentials=creds)
            
            # Build query
            search_query = query or ""
            if unread_only:
                search_query = f"is:unread {search_query}".strip()
            
            # Get messages
            messages_result = service.users().messages().list(
                userId='me',
                q=search_query,
                maxResults=max_results
            ).execute()
            
            messages = messages_result.get('messages', [])
            
            if not messages:
                return "No emails found."
            
            result = f"Found {len(messages)} emails:\n\n"
            
            for message in messages:
                msg = service.users().messages().get(userId='me', id=message['id'], format='metadata', metadataHeaders=['From', 'Subject', 'Date']).execute()
                
                headers = msg['payload']['headers']
                from_header = next((h['value'] for h in headers if h['name'] == 'From'), 'Unknown')
                subject_header = next((h['value'] for h in headers if h['name'] == 'Subject'), 'No Subject')
                date_header = next((h['value'] for h in headers if h['name'] == 'Date'), 'Unknown')
                
                # Parse date
                try:
                    date_str = date_header.split(',')[1].strip()
                    date_obj = datetime.strptime(date_str, '%d %b %Y %H:%M:%S %Z')
                    formatted_date = date_obj.strftime('%Y-%m-%d %H:%M')
                except:
                    formatted_date = date_header
                
                # Check if unread
                is_unread = 'UNREAD' in msg.get('labelIds', [])
                
                result += f"{'🔴' if is_unread else '🔵'} {subject_header}\n"
                result += f"   From: {from_header}\n"
                result += f"   Date: {formatted_date}\n"
                result += f"   ID: {message['id']}\n\n"
            
            logger.info(f"Retrieved {len(messages)} emails")
            return result
            
        except Exception as e:
            logger.error(f"Failed to get emails: {str(e)}", exc_info=True)
            return f"Error getting emails: {str(e)}"


class ReadEmailTool(BaseTool):
    """Read the full content of a specific email."""
    
    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="read_email",
            description="Read the full content of a specific email by ID.",
            parameters=[
                ToolParameter(
                    name="message_id",
                    type="string",
                    description="Gmail message ID",
                    required=True
                )
            ],
            return_type="string"
        )
    
    def execute(self, message_id: str, **kwargs) -> str:
        try:
            creds = get_google_credentials()
            service = build('gmail', 'v1', credentials=creds)
            
            # Get full message
            message = service.users().messages().get(userId='me', id=message_id, format='full').execute()
            
            # Extract headers
            headers = message['payload']['headers']
            from_header = next((h['value'] for h in headers if h['name'] == 'From'), 'Unknown')
            subject_header = next((h['value'] for h in headers if h['name'] == 'Subject'), 'No Subject')
            date_header = next((h['value'] for h in headers if h['name'] == 'Date'), 'Unknown')
            to_header = next((h['value'] for h in headers if h['name'] == 'To'), 'Unknown')
            
            result = f"Subject: {subject_header}\n"
            result += f"From: {from_header}\n"
            result += f"To: {to_header}\n"
            result += f"Date: {date_header}\n\n"
            
            # Extract body
            if 'parts' in message['payload']:
                # Multipart message
                for part in message['payload']['parts']:
                    if part['mimeType'] == 'text/plain':
                        data = part['body']['data']
                        text = base64.urlsafe_b64decode(data).decode('utf-8')
                        result += f"Body:\n{text}"
                        break
            else:
                # Single part message
                if message['payload']['mimeType'] == 'text/plain':
                    data = message['payload']['body']['data']
                    text = base64.urlsafe_b64decode(data).decode('utf-8')
                    result += f"Body:\n{text}"
                elif message['payload']['mimeType'] == 'text/html':
                    data = message['payload']['body']['data']
                    html = base64.urlsafe_b64decode(data).decode('utf-8')
                    result += f"Body (HTML):\n{html[:1000]}..."
            
            logger.info(f"Read email: {message_id}")
            return result
            
        except Exception as e:
            logger.error(f"Failed to read email: {str(e)}", exc_info=True)
            return f"Error reading email: {str(e)}"


class SendEmailTool(BaseTool):
    """Send an email using Gmail."""
    
    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="send_email",
            description="Send an email using Gmail.",
            parameters=[
                ToolParameter(
                    name="to",
                    type="string",
                    description="Recipient email address",
                    required=True
                ),
                ToolParameter(
                    name="subject",
                    type="string",
                    description="Email subject",
                    required=True
                ),
                ToolParameter(
                    name="body",
                    type="string",
                    description="Email body text",
                    required=True
                )
            ],
            return_type="string"
        )
    
    def execute(self, to: str, subject: str, body: str, **kwargs) -> str:
        try:
            creds = get_google_credentials()
            service = build('gmail', 'v1', credentials=creds)
            
            # Create message
            message = email.message.EmailMessage()
            message.set_content(body)
            message['to'] = to
            message['subject'] = subject
            
            # Encode message
            encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')
            
            # Send message
            send_message = {'raw': encoded_message}
            result = service.users().messages().send(userId='me', body=send_message).execute()
            
            logger.info(f"Sent email to {to}")
            return f"Email sent successfully! Message ID: {result['id']}\nTo: {to}\nSubject: {subject}"
            
        except Exception as e:
            logger.error(f"Failed to send email: {str(e)}", exc_info=True)
            return f"Error sending email: {str(e)}"


class MarkEmailAsReadTool(BaseTool):
    """Mark an email as read."""
    
    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="mark_email_as_read",
            description="Mark an email as read by removing the UNREAD label.",
            parameters=[
                ToolParameter(
                    name="message_id",
                    type="string",
                    description="Gmail message ID",
                    required=True
                )
            ],
            return_type="string"
        )
    
    def execute(self, message_id: str, **kwargs) -> str:
        try:
            creds = get_google_credentials()
            service = build('gmail', 'v1', credentials=creds)
            
            # Remove UNREAD label
            service.users().messages().modify(
                userId='me',
                id=message_id,
                body={'removeLabelIds': ['UNREAD']}
            ).execute()
            
            logger.info(f"Marked email as read: {message_id}")
            return f"Email marked as read: {message_id}"
            
        except Exception as e:
            logger.error(f"Failed to mark email as read: {str(e)}", exc_info=True)
            return f"Error marking email as read: {str(e)}"


class GetUnreadEmailsTool(BaseTool):
    """Get only unread emails from Gmail."""
    
    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="get_unread_emails",
            description="Get only unread emails from Gmail inbox.",
            parameters=[
                ToolParameter(
                    name="max_results",
                    type="integer",
                    description="Maximum number of unread emails to return (default: 10)",
                    required=False
                )
            ],
            return_type="string"
        )
    
    def execute(self, max_results: int = 10, **kwargs) -> str:
        try:
            creds = get_google_credentials()
            service = build('gmail', 'v1', credentials=creds)
            
            # Get unread messages
            messages_result = service.users().messages().list(
                userId='me',
                q='is:unread',
                maxResults=max_results
            ).execute()
            
            messages = messages_result.get('messages', [])
            
            if not messages:
                return "No unread emails found."
            
            result = f"Found {len(messages)} unread emails:\n\n"
            
            for message in messages:
                msg = service.users().messages().get(userId='me', id=message['id'], format='metadata', metadataHeaders=['From', 'Subject', 'Date']).execute()
                
                headers = msg['payload']['headers']
                from_header = next((h['value'] for h in headers if h['name'] == 'From'), 'Unknown')
                subject_header = next((h['value'] for h in headers if h['name'] == 'Subject'), 'No Subject')
                date_header = next((h['value'] for h in headers if h['name'] == 'Date'), 'Unknown')
                
                # Parse date
                try:
                    date_str = date_header.split(',')[1].strip()
                    date_obj = datetime.strptime(date_str, '%d %b %Y %H:%M:%S %Z')
                    formatted_date = date_obj.strftime('%Y-%m-%d %H:%M')
                except:
                    formatted_date = date_header
                
                result += f"🔴 {subject_header}\n"
                result += f"   From: {from_header}\n"
                result += f"   Date: {formatted_date}\n"
                result += f"   ID: {message['id']}\n\n"
            
            logger.info(f"Retrieved {len(messages)} unread emails")
            return result
            
        except Exception as e:
            logger.error(f"Failed to get unread emails: {str(e)}", exc_info=True)
            return f"Error getting unread emails: {str(e)}"
