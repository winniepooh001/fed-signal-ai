# agents/email_agent.py
import io
import json
import os
import smtplib
from datetime import datetime
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict, List, Optional, Type

import pandas as pd
from langchain.tools import BaseTool

from schema.tool_schemas import EmailAgentInput
from utils.logging_config import get_logger

logger = get_logger()


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
            "smtp_server": os.getenv("SMTP_SERVER", "smtp.gmail.com"),
            "smtp_port": int(os.getenv("SMTP_PORT", "587")),
            "sender_email": os.getenv("SENDER_EMAIL"),
            "sender_password": os.getenv("SENDER_PASSWORD"),
            "sender_name": os.getenv("SENDER_NAME", "TradingView Screener Agent"),
        }

    def _run(
        self,
        recipient_emails: List[str],
        screener_result_id: str,
        subject_prefix: str = "TradingView Screener Results",
        include_csv: bool = True,
        custom_message: Optional[str] = None,
    ) -> str:
        """Send email with screener results"""

        try:
            # Validate SMTP configuration
            if (
                not self._smtp_config["sender_email"]
                or not self._smtp_config["sender_password"]
            ):
                return json.dumps(
                    {
                        "success": False,
                        "error": "SMTP configuration incomplete. Please set SENDER_EMAIL and SENDER_PASSWORD environment variables.",
                    }
                )

            # Get screener data from database
            screener_data = self._get_screener_data(screener_result_id)
            if not screener_data:
                return json.dumps(
                    {
                        "success": False,
                        "error": f"Screener result {screener_result_id} not found",
                    }
                )

            # Generate email content
            html_content = self._generate_html_report(screener_data, custom_message)

            # Create email message
            msg = MIMEMultipart("alternative")
            msg["Subject"] = (
                f"{subject_prefix} - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            )
            msg["From"] = (
                f"{self._smtp_config['sender_name']} <{self._smtp_config['sender_email']}>"
            )

            # Add HTML content
            html_part = MIMEText(html_content, "html")
            msg.attach(html_part)

            # Add CSV attachment if requested
            if include_csv and screener_data["results"]:
                csv_attachment = self._create_csv_attachment(screener_data)
                msg.attach(csv_attachment)

            # Send email
            with smtplib.SMTP(
                self._smtp_config["smtp_server"], self._smtp_config["smtp_port"]
            ) as server:
                server.starttls()
                server.login(
                    self._smtp_config["sender_email"],
                    self._smtp_config["sender_password"],
                )

                for recipient in recipient_emails:
                    msg["To"] = recipient
                    server.send_message(msg)
                    del msg["To"]

            # Log to database
            self._log_email_sent(
                screener_result_id, recipient_emails, len(screener_data["results"])
            )

            logger.info(
                f"Email sent successfully to {len(recipient_emails)} recipients"
            )

            return json.dumps(
                {
                    "success": True,
                    "screener_result_id": screener_result_id,
                    "recipients": recipient_emails,
                    "stocks_sent": len(screener_data["results"]),
                    "included_csv": include_csv,
                    "sent_at": datetime.now().isoformat(),
                }
            )

        except Exception as e:
            logger.error(f"Email sending error: {str(e)}")
            return json.dumps(
                {
                    "success": False,
                    "error": str(e),
                    "screener_result_id": screener_result_id,
                    "attempted_at": datetime.now().isoformat(),
                }
            )

    def _get_screener_data(self, screener_result_id: str) -> Optional[Dict]:
        """Retrieve screener data from database"""
        if not self._db_manager:
            return None

        try:
            with self._db_manager.get_session() as session:
                from database.models import (
                    AgentExecution,
                    ScreenerInput,
                    ScreenerResult,
                )

                result = (
                    session.query(ScreenerResult)
                    .join(ScreenerInput)
                    .join(AgentExecution)
                    .filter(ScreenerResult.id == screener_result_id)
                    .first()
                )

                if not result:
                    return None

                return {
                    "result_id": result.id,
                    "input_id": result.screener_input_id,
                    "execution_id": result.screener_input.agent_execution_id,
                    "total_results": result.total_results,
                    "returned_results": result.returned_results,
                    "results": (
                        json.loads(result.result_data) if result.result_data else []
                    ),
                    "execution_time_ms": result.execution_time_ms,
                    "query_executed_at": result.query_executed_at,
                    "success": result.success,
                    # Input details
                    "columns": json.loads(result.screener_input.columns),
                    "filters": json.loads(result.screener_input.filters),
                    "sort_column": result.screener_input.sort_column,
                    "sort_ascending": result.screener_input.sort_ascending,
                    "limit": result.screener_input.limit,
                    "query_reasoning": result.screener_input.query_reasoning,
                    # Execution context
                    "user_prompt": result.screener_input.agent_execution.user_prompt,
                    "agent_reasoning": result.screener_input.agent_execution.agent_reasoning,
                    "execution_type": result.screener_input.agent_execution.execution_type,
                }

        except Exception as e:
            logger.error(f"Error retrieving screener data: {e}")
            return None

    def _generate_html_report(
        self, screener_data: Dict, custom_message: Optional[str] = None
    ) -> str:
        """Generate professional HTML email report with clear sections"""

        results = screener_data["results"][:20]  # Limit to top 20 for email

        # Create filter summary
        filter_summary = self._format_filters(screener_data["filters"])

        # Parse custom message for better formatting
        analysis_sections = (
            self._parse_analysis_sections(custom_message) if custom_message else {}
        )

        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{ 
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
                    margin: 0; 
                    padding: 20px; 
                    background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
                    line-height: 1.6;
                }}
                .container {{ 
                    max-width: 900px; 
                    margin: 0 auto; 
                    background-color: white; 
                    border-radius: 12px; 
                    overflow: hidden;
                    box-shadow: 0 8px 32px rgba(0,0,0,0.1); 
                }}

                /* Header Section */
                .header {{ 
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white; 
                    text-align: center; 
                    padding: 40px 30px;
                }}
                .header h1 {{ 
                    margin: 0 0 10px 0; 
                    font-size: 32px; 
                    font-weight: 700;
                    text-shadow: 0 2px 4px rgba(0,0,0,0.3);
                }}
                .header p {{ 
                    margin: 0; 
                    font-size: 18px; 
                    opacity: 0.9;
                }}

                /* Main Content Padding */
                .content {{ padding: 40px 30px; }}

                /* Summary Stats Section */
                .summary {{ 
                    background: linear-gradient(135deg, #e3f2fd 0%, #bbdefb 100%); 
                    padding: 30px; 
                    border-radius: 12px; 
                    margin-bottom: 30px;
                    box-shadow: 0 4px 16px rgba(33, 150, 243, 0.15);
                }}
                .summary h2 {{ 
                    margin: 0 0 20px 0; 
                    color: #1976D2; 
                    font-size: 24px; 
                    font-weight: 600;
                    display: flex;
                    align-items: center;
                }}
                .summary h2::before {{
                    content: "📊";
                    margin-right: 10px;
                    font-size: 28px;
                }}
                .summary-grid {{ 
                    display: grid; 
                    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); 
                    gap: 20px; 
                }}
                .summary-item {{ 
                    text-align: center; 
                    background: white;
                    padding: 20px;
                    border-radius: 8px;
                    box-shadow: 0 2px 8px rgba(0,0,0,0.1);
                }}
                .summary-number {{ 
                    font-size: 28px; 
                    font-weight: bold; 
                    color: #1976D2; 
                    display: block; 
                    margin-bottom: 5px;
                }}
                .summary-label {{ 
                    font-size: 14px; 
                    color: #666; 
                    text-transform: uppercase; 
                    font-weight: 600;
                    letter-spacing: 0.5px;
                }}

                /* Analysis Section Styles */
                .analysis-section {{
                    background: linear-gradient(135deg, #fff8e1 0%, #ffecb3 100%);
                    border-radius: 12px;
                    margin-bottom: 30px;
                    overflow: hidden;
                    box-shadow: 0 4px 16px rgba(255, 193, 7, 0.15);
                }}

                .analysis-header {{
                    background: linear-gradient(135deg, #ff9800 0%, #f57c00 100%);
                    color: white;
                    padding: 20px 30px;
                    font-size: 20px;
                    font-weight: 600;
                    display: flex;
                    align-items: center;
                }}
                .analysis-header::before {{
                    content: "🎯";
                    margin-right: 10px;
                    font-size: 24px;
                }}

                .analysis-content {{
                    padding: 30px;
                }}

                .analysis-subsection {{
                    margin-bottom: 25px;
                    background: white;
                    border-radius: 8px;
                    padding: 20px;
                    box-shadow: 0 2px 8px rgba(0,0,0,0.05);
                }}

                .analysis-subsection h4 {{
                    margin: 0 0 15px 0;
                    color: #e65100;
                    font-size: 16px;
                    font-weight: 600;
                    text-transform: uppercase;
                    letter-spacing: 0.5px;
                    border-bottom: 2px solid #ffcc02;
                    padding-bottom: 8px;
                }}

                .analysis-subsection p {{
                    margin: 0;
                    color: #444;
                    line-height: 1.7;
                }}

                /* Filters Section */
                .filters {{ 
                    background: linear-gradient(135deg, #e8f5e8 0%, #c8e6c9 100%); 
                    border-radius: 12px; 
                    margin-bottom: 30px;
                    overflow: hidden;
                    box-shadow: 0 4px 16px rgba(76, 175, 80, 0.15);
                }}
                .filters-header {{
                    background: linear-gradient(135deg, #4caf50 0%, #388e3c 100%);
                    color: white;
                    padding: 20px 30px;
                    font-size: 20px;
                    font-weight: 600;
                    display: flex;
                    align-items: center;
                }}
                .filters-header::before {{
                    content: "🔍";
                    margin-right: 10px;
                    font-size: 24px;
                }}
                .filters-content {{
                    padding: 30px;
                }}
                .filter-list {{ 
                    list-style: none; 
                    padding: 0; 
                    margin: 0; 
                }}
                .filter-item {{ 
                    background: white; 
                    padding: 15px 20px; 
                    margin: 10px 0; 
                    border-radius: 8px; 
                    border-left: 4px solid #4caf50;
                    box-shadow: 0 2px 8px rgba(0,0,0,0.05);
                    font-weight: 500;
                }}

                /* Stock Results Section */
                .stocks-header {{
                    color: #1976D2;
                    font-size: 24px;
                    font-weight: 600;
                    margin: 0 0 25px 0;
                    display: flex;
                    align-items: center;
                }}
                .stocks-header::before {{
                    content: "🏆";
                    margin-right: 10px;
                    font-size: 28px;
                }}

                .stocks-table {{ 
                    width: 100%; 
                    border-collapse: collapse; 
                    border-radius: 12px;
                    overflow: hidden;
                    box-shadow: 0 4px 16px rgba(0,0,0,0.1);
                }}
                .stocks-table th {{ 
                    background: linear-gradient(135deg, #1976d2 0%, #2196f3 100%); 
                    color: white; 
                    padding: 18px 12px; 
                    text-align: left; 
                    font-size: 14px; 
                    font-weight: 600;
                    text-transform: uppercase;
                    letter-spacing: 0.5px;
                }}
                .stocks-table td {{ 
                    padding: 15px 12px; 
                    border-bottom: 1px solid #e0e0e0; 
                    font-size: 14px;
                    background: white;
                }}
                .stocks-table tbody tr:hover {{ 
                    background-color: #f8f9fa !important; 
                }}
                .stocks-table tbody tr:nth-child(even) {{ 
                    background-color: #fafafa; 
                }}
                .stocks-table tbody tr:first-child td {{
                    background: linear-gradient(135deg, #fff3e0 0%, #ffe0b2 100%);
                    font-weight: 600;
                }}
                .positive {{ 
                    color: #4caf50; 
                    font-weight: bold; 
                }}
                .negative {{ 
                    color: #f44336; 
                    font-weight: bold; 
                }}
                .rank-number {{
                    background: #1976D2;
                    color: white;
                    padding: 4px 8px;
                    border-radius: 4px;
                    font-size: 12px;
                    font-weight: bold;
                }}

                /* Footer Section */
                .footer {{ 
                    text-align: center; 
                    margin-top: 40px; 
                    padding: 30px; 
                    background: linear-gradient(135deg, #f5f5f5 0%, #e0e0e0 100%);
                    color: #666; 
                    font-size: 13px;
                    border-radius: 12px;
                }}

                /* Disclaimer */
                .disclaimer {{ 
                    background: linear-gradient(135deg, #fff8e1 0%, #ffecb3 100%); 
                    padding: 25px; 
                    border-radius: 12px; 
                    margin: 30px 0; 
                    border-left: 6px solid #ffc107;
                    box-shadow: 0 4px 16px rgba(255, 193, 7, 0.15);
                }}
                .disclaimer p {{ 
                    margin: 0; 
                    font-size: 13px; 
                    color: #bf6000; 
                    line-height: 1.6;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>📊 TradingView Screener Results</h1>
                    <p>Generated on {datetime.now().strftime('%B %d, %Y at %I:%M %p')}</p>
                </div>

                <div class="content">
                    <div class="summary">
                        <h2>Screening Summary</h2>
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

                    {self._generate_analysis_section_html(analysis_sections)}

                    <div class="filters">
                        <div class="filters-header">Filter Criteria</div>
                        <div class="filters-content">
                            <ul class="filter-list">
                                {filter_summary}
                            </ul>
                        </div>
                    </div>

                    <h3 class="stocks-header">Top Stock Results</h3>
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
            name = stock.get("name", "N/A")
            close = stock.get("close", 0)
            change = stock.get("change", 0)
            volume = stock.get("volume", 0)
            market_cap = stock.get("market_cap_basic", 0)

            change_class = "positive" if change > 0 else "negative"

            html += f"""
                            <tr>
                                <td><span class="rank-number">#{i}</span></td>
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
                </div>

                <div class="footer">
                    <p><strong>Generated by TradingView Screener Agent</strong></p>
                    <p>Execution ID: {screener_data['execution_id']} | Data sourced from TradingView at {screener_data['query_executed_at']}</p>
                </div>
            </div>
        </body>
        </html>
        """

        return html

    def _parse_analysis_sections(self, custom_message: str) -> Dict[str, str]:
        """Parse the custom message into structured sections"""
        sections = {}

        if not custom_message:
            return sections

        # Look for different section patterns
        lines = custom_message.split("\n")
        current_section = None
        current_content = []

        for line in lines:
            line = line.strip()

            # Check for section headers (lines with colons or specific patterns)
            if any(
                header in line.lower()
                for header in [
                    "fed analysis",
                    "market movement",
                    "market commentary",
                    "fed source",
                    "screening strategy",
                ]
            ):
                # Save previous section
                if current_section and current_content:
                    sections[current_section] = "\n".join(current_content).strip()

                # Start new section
                if "fed analysis" in line.lower():
                    current_section = "Fed Analysis Summary"
                elif (
                    "market movement" in line.lower()
                    or "market commentary" in line.lower()
                ):
                    current_section = "Market Movement Analysis"
                elif "fed source" in line.lower():
                    current_section = "Fed Source Documents"
                elif "screening strategy" in line.lower():
                    current_section = "Screening Strategy"
                else:
                    current_section = line.replace(":", "").strip()

                current_content = []
            elif line and current_section:
                # Add content to current section
                current_content.append(line)

        # Save last section
        if current_section and current_content:
            sections[current_section] = "\n".join(current_content).strip()

        return sections

    def _generate_analysis_section_html(self, analysis_sections: Dict[str, str]) -> str:
        """Generate HTML for the analysis section with clear subsections"""

        if not analysis_sections:
            return ""

        html = """
        <div class="analysis-section">
            <div class="analysis-header">Analysis Rationale</div>
            <div class="analysis-content">
        """

        for section_title, section_content in analysis_sections.items():
            if section_content.strip():
                # Clean up content - remove HTML tags and format nicely
                clean_content = section_content.replace(
                    '<div class="reasoning-content">', ""
                ).replace("</div>", "")
                clean_content = clean_content.replace(
                    '<div class="reasoning-subheader">', ""
                ).replace('<div class="reasoning-header">', "")

                html += f"""
                <div class="analysis-subsection">
                    <h4>{section_title}</h4>
                    <p>{clean_content}</p>
                </div>
                """

        html += """
            </div>
        </div>
        """

        return html

    def _format_filters(self, filters: List[Dict]) -> str:
        """Format filters for display in email"""
        if not filters:
            return "<li class='filter-item'>No additional filters applied</li>"

        filter_html = ""
        for f in filters:
            filter_type = f.get("type", "unknown")
            column = f.get("column", "unknown")
            value = f.get("value")
            min_value = f.get("min_value")
            max_value = f.get("max_value")
            values = f.get("values", [])

            if filter_type == "greater_than":
                filter_html += f"<li class='filter-item'><strong>{column}</strong> > {value:,}</li>"
            elif filter_type == "less_than":
                filter_html += f"<li class='filter-item'><strong>{column}</strong> < {value:,}</li>"
            elif (
                filter_type == "range"
                and min_value is not None
                and max_value is not None
            ):
                filter_html += f"<li class='filter-item'><strong>{column}</strong> between {min_value:,} and {max_value:,}</li>"
            elif filter_type == "equals":
                filter_html += (
                    f"<li class='filter-item'><strong>{column}</strong> = {value}</li>"
                )
            elif filter_type == "in" and values:
                filter_html += f"<li class='filter-item'><strong>{column}</strong> in [{', '.join(map(str, values))}]</li>"
            else:
                filter_html += f"<li class='filter-item'><strong>{column}</strong> {filter_type} filter</li>"

        return filter_html

    def _create_csv_attachment(self, screener_data: Dict) -> MIMEBase:
        """Create CSV attachment with full results"""
        # Convert results to DataFrame
        df = pd.DataFrame(screener_data["results"])

        # Create CSV in memory
        csv_buffer = io.StringIO()
        df.to_csv(csv_buffer, index=False)
        csv_content = csv_buffer.getvalue()

        # Create attachment
        attachment = MIMEBase("application", "octet-stream")
        attachment.set_payload(csv_content.encode("utf-8"))
        encoders.encode_base64(attachment)

        filename = f"screener_results_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
        attachment.add_header(
            "Content-Disposition", f"attachment; filename= {filename}"
        )

        return attachment

    def _log_email_sent(
        self, screener_result_id: str, recipients: List[str], stock_count: int
    ):
        """Log email sending to database"""
        try:
            logger.info(
                f"Email sent - Result ID: {screener_result_id}, Recipients: {len(recipients)}, Stocks: {stock_count}"
            )
        except Exception as e:
            logger.error(f"Error logging email: {e}")


# Standalone email workflow function
def send_screener_email(
    db_manager,
    screener_result_id: str,
    recipient_emails: List[str],
    custom_message: Optional[str] = None,
    smtp_config: Optional[Dict] = None,
) -> Dict[str, Any]:
    """
    Standalone function to send screener results via email

    Args:
        db_manager: Database manager instance
        screener_result_id: ID of the screener result to send
        recipient_emails: List of email addresses
        custom_message: Optional custom message
        smtp_config: Optional SMTP configuration

    Returns:
        Dict with success status and details
    """

    logger.info(f"Sending screener email for result ID: {screener_result_id}")

    try:
        # Create email agent
        email_agent = EmailAgent(db_manager=db_manager, smtp_config=smtp_config)

        # Send email
        result_json = email_agent._run(
            recipient_emails=recipient_emails,
            screener_result_id=screener_result_id,
            custom_message=custom_message,
        )

        result = json.loads(result_json)

        if result["success"]:
            logger.info(
                f"Email sent successfully to {len(recipient_emails)} recipients"
            )
        else:
            logger.error(f"Email sending failed: {result.get('error')}")

        return result

    except Exception as e:
        logger.error(f"Email workflow error: {e}")
        return {
            "success": False,
            "error": str(e),
            "timestamp": datetime.now().isoformat(),
        }
