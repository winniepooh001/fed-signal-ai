# tools/email_agent.py
from langchain.tools import BaseTool
from typing import Type, Optional, Dict, Any, List
import smtplib
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime
import logging
import pandas as pd
import io
import os

from schema.tool_schemas import EmailAgentInput

logger = logging.getLogger(__name__)


class EmailAgent(BaseTool):
    """Enhanced email agent for sending curated screener results"""

    name: str = "email_agent"
    description: str = """
    Sends professional email reports with curated stock lists, filter criteria, 
    and analysis rationale. Supports HTML formatting and CSV attachments.
    """
    args_schema: Type[EmailAgentInput] = EmailAgentInput

    # Use class variables to avoid Pydantic issues
    _db_manager = None
    _smtp_config = None

    def __init__(self, db_manager=None, smtp_config: Optional[Dict] = None):
        super().__init__()
        EmailAgent._db_manager = db_manager
        EmailAgent._smtp_config = smtp_config or self._get_default_smtp_config()

    def _get_default_smtp_config(self) -> Dict:
        """Get SMTP configuration from environment variables"""
        return {
            'smtp_server': os.getenv('SMTP_SERVER', 'smtp.gmail.com'),
            'smtp_port': int(os.getenv('SMTP_PORT', '587')),
            'sender_email': os.getenv('SENDER_EMAIL'),
            'sender_password': os.getenv('SENDER_PASSWORD'),
            'sender_name': os.getenv('SENDER_NAME', 'TradingView Screener Agent')
        }

    def _run(self,
             recipient_emails: List[str],
             screener_result_id: str,
             subject_prefix: str = "TradingView Screener Results",
             include_csv: bool = True,
             custom_message: Optional[str] = None) -> str:
        """Send email with screener results"""

        try:
            # Get screener data from database
            screener_data = self._get_screener_data(screener_result_id)
            if not screener_data:
                return json.dumps({
                    'success': False,
                    'error': f'Screener result {screener_result_id} not found'
                })

            # Generate email content
            html_content = self._generate_html_report(screener_data, custom_message)

            # Create email message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = f"{subject_prefix} - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            msg['From'] = f"{self._smtp_config['sender_name']} <{self._smtp_config['sender_email']}>"
            msg['To'] = ', '.join(recipient_emails)

            # Add HTML content
            html_part = MIMEText(html_content, 'html')
            msg.attach(html_part)

            # Add CSV attachment if requested
            if include_csv and screener_data['results']:
                csv_attachment = self._create_csv_attachment(screener_data)
                msg.attach(csv_attachment)

            # Send email
            with smtplib.SMTP(self._smtp_config['smtp_server'], self._smtp_config['smtp_port']) as server:
                server.starttls()
                server.login(self._smtp_config['sender_email'], self._smtp_config['sender_password'])

                for recipient in recipient_emails:
                    msg['To'] = recipient
                    server.send_message(msg)
                    del msg['To']

            # Log to database
            self._log_email_sent(screener_result_id, recipient_emails, len(screener_data['results']))

            return json.dumps({
                'success': True,
                'screener_result_id': screener_result_id,
                'recipients': recipient_emails,
                'stocks_sent': len(screener_data['results']),
                'included_csv': include_csv,
                'sent_at': datetime.now().isoformat()
            })

        except Exception as e:
            logger.error(f"Email sending error: {str(e)}")
            return json.dumps({
                'success': False,
                'error': str(e),
                'screener_result_id': screener_result_id,
                'attempted_at': datetime.now().isoformat()
            })

    def _get_screener_data(self, screener_result_id: str) -> Optional[Dict]:
        """Retrieve screener data from database"""
        if not self._db_manager:
            return None

        try:
            with self._db_manager.get_session() as session:
                from database.models import ScreenerResult, ScreenerInput, AgentExecution

                result = session.query(ScreenerResult) \
                    .join(ScreenerInput) \
                    .join(AgentExecution) \
                    .filter(ScreenerResult.id == screener_result_id) \
                    .first()

                if not result:
                    return None

                return {
                    'result_id': result.id,
                    'input_id': result.screener_input_id,
                    'execution_id': result.screener_input.agent_execution_id,
                    'total_results': result.total_results,
                    'returned_results': result.returned_results,
                    'results': json.loads(result.result_data) if result.result_data else [],
                    'execution_time_ms': result.execution_time_ms,
                    'query_executed_at': result.query_executed_at,
                    'success': result.success,

                    # Input details
                    'columns': json.loads(result.screener_input.columns),
                    'filters': json.loads(result.screener_input.filters),
                    'sort_column': result.screener_input.sort_column,
                    'sort_ascending': result.screener_input.sort_ascending,
                    'limit': result.screener_input.limit,
                    'query_reasoning': result.screener_input.query_reasoning,

                    # Execution context
                    'user_prompt': result.screener_input.agent_execution.user_prompt,
                    'agent_reasoning': result.screener_input.agent_execution.agent_reasoning,
                    'execution_type': result.screener_input.agent_execution.execution_type,
                }

        except Exception as e:
            logger.error(f"Error retrieving screener data: {e}")
            return None

    def _generate_html_report(self, screener_data: Dict, custom_message: Optional[str] = None) -> str:
        """Generate professional HTML email report"""

        results = screener_data['results'][:20]  # Limit to top 20 for email

        # Create filter summary
        filter_summary = self._format_filters(screener_data['filters'])

        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5; }}
                .container {{ max-width: 800px; margin: 0 auto; background-color: white; padding: 30px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }}
                .header {{ text-align: center; border-bottom: 3px solid #2196F3; padding-bottom: 20px; margin-bottom: 30px; }}
                .header h1 {{ color: #1976D2; margin: 0; font-size: 28px; }}
                .header p {{ color: #666; margin: 5px 0 0 0; font-size: 16px; }}
                .summary {{ background: linear-gradient(135deg, #e3f2fd 0%, #bbdefb 100%); padding: 20px; border-radius: 8px; margin-bottom: 25px; }}
                .summary h2 {{ margin: 0 0 15px 0; color: #1976D2; font-size: 20px; }}
                .summary-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 15px; }}
                .summary-item {{ text-align: center; }}
                .summary-number {{ font-size: 24px; font-weight: bold; color: #1976D2; display: block; }}
                .summary-label {{ font-size: 12px; color: #666; text-transform: uppercase; }}
                .reasoning {{ background-color: #fff3e0; padding: 20px; border-radius: 8px; margin-bottom: 25px; border-left: 4px solid #ff9800; }}
                .reasoning h3 {{ margin: 0 0 10px 0; color: #e65100; font-size: 18px; }}
                .filters {{ background-color: #f1f8e9; padding: 20px; border-radius: 8px; margin-bottom: 25px; }}
                .filters h3 {{ margin: 0 0 15px 0; color: #388e3c; font-size: 18px; }}
                .filter-list {{ list-style: none; padding: 0; margin: 0; }}
                .filter-item {{ background: white; padding: 8px 12px; margin: 5px 0; border-radius: 5px; border-left: 3px solid #4caf50; }}
                .stocks-table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
                .stocks-table th {{ background: linear-gradient(135deg, #1976d2 0%, #2196f3 100%); color: white; padding: 12px 8px; text-align: left; font-size: 14px; }}
                .stocks-table td {{ padding: 10px 8px; border-bottom: 1px solid #e0e0e0; font-size: 13px; }}
                .stocks-table tbody tr:hover {{ background-color: #f5f5f5; }}
                .stocks-table tbody tr:nth-child(even) {{ background-color: #fafafa; }}
                .positive {{ color: #4caf50; font-weight: bold; }}
                .negative {{ color: #f44336; font-weight: bold; }}
                .footer {{ text-align: center; margin-top: 30px; padding-top: 20px; border-top: 2px solid #e0e0e0; color: #666; font-size: 12px; }}
                .disclaimer {{ background-color: #fff8e1; padding: 15px; border-radius: 8px; margin-top: 20px; border-left: 4px solid #ffc107; }}
                .disclaimer p {{ margin: 0; font-size: 12px; color: #bf6000; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>📊 TradingView Screener Results</h1>
                    <p>Generated on {datetime.now().strftime('%B %d, %Y at %I:%M %p')}</p>
                </div>

                <div class="summary">
                    <h2>📈 Screening Summary</h2>
                    <div class="summary-grid">
                        <div class="summary-item">
                            <span class="summary-number">{screener_data['total_results']:,}</span>
                            <span class="summary-label">Total Matches</span>
                        </div>
                        <div class="summary-item">
                            <span class="summary-number">{len(results)}</span>
                            <span class="summary-label">Top Results</span>
                        </div>
                        <div class="summary-item">
                            <span class="summary-number">{screener_data['execution_time_ms']:.0f}ms</span>
                            <span class="summary-label">Query Time</span>
                        </div>
                        <div class="summary-item">
                            <span class="summary-number">{len(screener_data['filters'])}</span>
                            <span class="summary-label">Filters Applied</span>
                        </div>
                    </div>
                </div>

                {"<div class='reasoning'><h3>🎯 Analysis Rationale</h3><p>" + (screener_data.get('query_reasoning') or screener_data.get('agent_reasoning', 'Systematic screening based on current market conditions.')) + "</p></div>" if screener_data.get('query_reasoning') or screener_data.get('agent_reasoning') else ""}

                {"<div class='reasoning'><h3>💭 Custom Message</h3><p>" + custom_message + "</p></div>" if custom_message else ""}

                <div class="filters">
                    <h3>🔍 Filter Criteria</h3>
                    <ul class="filter-list">
                        {filter_summary}
                    </ul>
                </div>

                <h3>🏆 Top Stock Results</h3>
                <table class="stocks-table">
                    <thead>
                        <tr>
                            <th>Rank</th>
                            <th>Company</th>
                            <th>Price</th>
                            <th>Change %</th>
                            <th>Volume</th>
                            <th>Market Cap</th>
                        </tr>
                    </thead>
                    <tbody>
        """

        # Add stock rows
        for i, stock in enumerate(results, 1):
            name = stock.get('name', 'N/A')
            close = stock.get('close', 0)
            change = stock.get('change', 0)
            volume = stock.get('volume', 0)
            market_cap = stock.get('market_cap_basic', 0)

            change_class = 'positive' if change > 0 else 'negative'

            html += f"""
                        <tr>
                            <td><strong>#{i}</strong></td>
                            <td><strong>{name}</strong></td>
                            <td>${close:.2f}</td>
                            <td class="{change_class}">{change:+.2f}%</td>
                            <td>{volume:,.0f}</td>
                            <td>${market_cap:,.0f}</td>
                        </tr>
            """

        html += f"""
                    </tbody>
                </table>

                <div class="disclaimer">
                    <p><strong>Disclaimer:</strong> This is an automated screening result for informational purposes only. 
                    Not investment advice. Always conduct your own research and consult with financial professionals before making investment decisions. 
                    Past performance does not guarantee future results.</p>
                </div>

                <div class="footer">
                    <p>Generated by TradingView Screener Agent | Execution ID: {screener_data['execution_id']}</p>
                    <p>Data sourced from TradingView at {screener_data['query_executed_at']}</p>
                </div>
            </div>
        </body>
        </html>
        """

        return html

    def _format_filters(self, filters: List[Dict]) -> str:
        """Format filters for display in email"""
        if not filters:
            return "<li class='filter-item'>No additional filters applied</li>"

        filter_html = ""
        for f in filters:
            filter_type = f.get('type', 'unknown')
            column = f.get('column', 'unknown')
            value = f.get('value')
            min_value = f.get('min_value')
            max_value = f.get('max_value')

            if filter_type == 'greater_than':
                filter_html += f"<li class='filter-item'><strong>{column}</strong> > {value:,}</li>"
            elif filter_type == 'less_than':
                filter_html += f"<li class='filter-item'><strong>{column}</strong> < {value:,}</li>"
            elif filter_type == 'range' and min_value is not None and max_value is not None:
                filter_html += f"<li class='filter-item'><strong>{column}</strong> between {min_value:,} and {max_value:,}</li>"
            elif filter_type == 'equals':
                filter_html += f"<li class='filter-item'><strong>{column}</strong> = {value}</li>"
            else:
                filter_html += f"<li class='filter-item'><strong>{column}</strong> {filter_type} filter</li>"

        return filter_html

    def _create_csv_attachment(self, screener_data: Dict) -> MIMEBase:
        """Create CSV attachment with full results"""
        # Convert results to DataFrame
        df = pd.DataFrame(screener_data['results'])

        # Create CSV in memory
        csv_buffer = io.StringIO()
        df.to_csv(csv_buffer, index=False)
        csv_content = csv_buffer.getvalue()

        # Create attachment
        attachment = MIMEBase('application', 'octet-stream')
        attachment.set_payload(csv_content.encode('utf-8'))
        encoders.encode_base64(attachment)

        filename = f"screener_results_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
        attachment.add_header(
            'Content-Disposition',
            f'attachment; filename= {filename}'
        )

        return attachment

    def _log_email_sent(self, screener_result_id: str, recipients: List[str], stock_count: int):
        """Log email sending to database"""
        if not self._db_manager:
            return

        try:
            # This would require adding an EmailLog table to track sent emails
            # For now, just log to application logs
            logger.info(
                f"Email sent - Result ID: {screener_result_id}, Recipients: {len(recipients)}, Stocks: {stock_count}")
        except Exception as e:
            logger.error(f"Error logging email: {e}")


# schema/tool_schemas.py - Add this to your existing file
class EmailAgentInput(BaseModel):
    """Input schema for Email Agent"""
    recipient_emails: List[str] = Field(description="List of recipient email addresses")
    screener_result_id: str = Field(description="ID of the screener result to send")
    subject_prefix: str = Field(default="TradingView Screener Results", description="Email subject prefix")
    include_csv: bool = Field(default=True, description="Include CSV attachment")
    custom_message: Optional[str] = Field(None, description="Custom message to include in email")


# Enhanced ScreenerUpdateAgent with Email Integration
# Add this method to your existing ScreenerUpdateAgent class

def analyze_and_email_results(self,
                              fed_url: str,
                              recipient_emails: List[str],
                              target_content: str = "interest rates monetary policy",
                              custom_message: Optional[str] = None) -> Dict[str, Any]:
    """Complete workflow: analyze Fed data, create screeners, and email results"""

    # Step 1: Run the normal analysis
    analysis_result = self.analyze_fed_data_and_update_screeners(fed_url, target_content)

    if not analysis_result['success']:
        return analysis_result

    # Step 2: Find the screener result ID from the analysis
    screener_result_id = None
    intermediate_steps = analysis_result.get('intermediate_steps', [])

    for step in intermediate_steps:
        if len(step) >= 2 and hasattr(step[0], 'tool') and step[0].tool == 'tradingview_query':
            try:
                tool_result = json.loads(step[1])
                if tool_result.get('success') and tool_result.get('screener_result_id'):
                    screener_result_id = tool_result['screener_result_id']
                    break
            except:
                continue

    if not screener_result_id:
        return {
            'success': False,
            'error': 'No screener results found to email',
            'analysis_result': analysis_result
        }

    # Step 3: Send email with results
    email_tool = EmailAgent(db_manager=self.db_manager)
    email_result = email_tool._run(
        recipient_emails=recipient_emails,
        screener_result_id=screener_result_id,
        custom_message=custom_message
    )

    email_result_parsed = json.loads(email_result)

    return {
        'success': email_result_parsed['success'],
        'analysis_result': analysis_result,
        'email_result': email_result_parsed,
        'screener_result_id': screener_result_id,
        'workflow_completed_at': datetime.now().isoformat()
    }