#!/usr/bin/env python3
"""
Minimal Email Test Script
========================

Tests email functionality step by step to identify issues.
"""

import os
import sys
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv
import json
from datetime import datetime

# Load environment variables
load_dotenv()


def test_smtp_connection():
    """Test basic SMTP connection"""
    print("=" * 50)
    print("TEST 1: SMTP Connection")
    print("=" * 50)

    # Get SMTP configuration
    smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
    smtp_port = int(os.getenv('SMTP_PORT', '587'))
    sender_email = os.getenv('SENDER_EMAIL')
    sender_password = os.getenv('SENDER_PASSWORD')

    print(f"SMTP Server: {smtp_server}:{smtp_port}")
    print(f"Sender Email: {sender_email}")
    print(f"Password Set: {'Yes' if sender_password else 'No'}")

    if not sender_email or not sender_password:
        print("❌ MISSING CREDENTIALS")
        print("Set SENDER_EMAIL and SENDER_PASSWORD in .env file")
        return False

    try:
        print("\nTesting SMTP connection...")
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.set_debuglevel(1)  # Enable debug output
            server.starttls()
            server.login(sender_email, sender_password)
            print("✅ SMTP connection successful!")
            return True

    except smtplib.SMTPAuthenticationError as e:
        print(f"❌ AUTHENTICATION FAILED: {e}")
        print("For Gmail, make sure you're using an App Password, not your regular password")
        print("Guide: https://support.google.com/accounts/answer/185833")
        return False

    except smtplib.SMTPConnectError as e:
        print(f"❌ CONNECTION FAILED: {e}")
        print("Check your internet connection and SMTP server settings")
        return False

    except Exception as e:
        print(f"❌ SMTP ERROR: {e}")
        return False


def test_basic_email():
    """Test sending a basic text email"""
    print("\n" + "=" * 50)
    print("TEST 2: Basic Email Sending")
    print("=" * 50)

    # Get configuration
    smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
    smtp_port = int(os.getenv('SMTP_PORT', '587'))
    sender_email = os.getenv('SENDER_EMAIL')
    sender_password = os.getenv('SENDER_PASSWORD')
    sender_name = os.getenv('SENDER_NAME', 'Test System')

    # Get recipient
    recipient_emails_str = os.getenv('RECIPIENT_EMAILS')
    if not recipient_emails_str:
        recipient_email = input("Enter test recipient email: ").strip()
        if not recipient_email:
            print("❌ No recipient email provided")
            return False
        recipient_emails = [recipient_email]
    else:
        recipient_emails = [email.strip() for email in recipient_emails_str.split(',')]

    print(f"Recipients: {recipient_emails}")

    # Create simple email
    msg = MIMEText(
        "This is a test email from the TradingView Screener system.\n\nIf you receive this, email functionality is working correctly!")
    msg['Subject'] = f"Test Email - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    msg['From'] = f"{sender_name} <{sender_email}>"
    msg['To'] = ', '.join(recipient_emails)

    try:
        print("\nSending test email...")
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(sender_email, sender_password)

            for recipient in recipient_emails:
                server.send_message(msg, to_addrs=[recipient])
                print(f"✅ Email sent to: {recipient}")

        print("✅ BASIC EMAIL TEST SUCCESSFUL!")
        return True

    except Exception as e:
        print(f"❌ EMAIL SENDING FAILED: {e}")
        return False


def test_html_email():
    """Test sending HTML email with attachment simulation"""
    print("\n" + "=" * 50)
    print("TEST 3: HTML Email with Styling")
    print("=" * 50)

    # Get configuration
    smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
    smtp_port = int(os.getenv('SMTP_PORT', '587'))
    sender_email = os.getenv('SENDER_EMAIL')
    sender_password = os.getenv('SENDER_PASSWORD')
    sender_name = os.getenv('SENDER_NAME', 'Test System')

    recipient_emails_str = os.getenv('RECIPIENT_EMAILS')
    if not recipient_emails_str:
        print("❌ No RECIPIENT_EMAILS set - skipping HTML test")
        return False

    recipient_emails = [email.strip() for email in recipient_emails_str.split(',')]

    # Create HTML email
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; }
            .header { background-color: #2196F3; color: white; padding: 20px; text-align: center; }
            .content { padding: 20px; background-color: #f5f5f5; }
            .success { color: #4CAF50; font-weight: bold; }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>📧 Email Test Report</h1>
        </div>
        <div class="content">
            <h2>HTML Email Test</h2>
            <p>This email tests HTML formatting and styling capabilities.</p>

            <h3>Test Results:</h3>
            <ul>
                <li class="success">✅ HTML rendering</li>
                <li class="success">✅ CSS styling</li>
                <li class="success">✅ Email delivery</li>
            </ul>

            <p><strong>Timestamp:</strong> """ + datetime.now().strftime('%Y-%m-%d %H:%M:%S') + """</p>

            <hr>
            <p><em>This is an automated test email from the TradingView Screener system.</em></p>
        </div>
    </body>
    </html>
    """

    # Create multipart message
    msg = MIMEMultipart('alternative')
    msg['Subject'] = f"HTML Email Test - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    msg['From'] = f"{sender_name} <{sender_email}>"
    msg['To'] = ', '.join(recipient_emails)

    # Add HTML part
    html_part = MIMEText(html_content, 'html')
    msg.attach(html_part)

    try:
        print("Sending HTML email...")
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(sender_email, sender_password)

            for recipient in recipient_emails:
                server.send_message(msg, to_addrs=[recipient])
                print(f"✅ HTML email sent to: {recipient}")

        print("✅ HTML EMAIL TEST SUCCESSFUL!")
        return True

    except Exception as e:
        print(f"❌ HTML EMAIL FAILED: {e}")
        return False


def test_database_integration():
    """Test if database integration works for email system"""
    print("\n" + "=" * 50)
    print("TEST 4: Database Integration")
    print("=" * 50)

    try:
        # Import database components
        sys.path.append('.')
        from database import DatabaseManager

        print("Testing database connection...")
        db_manager = DatabaseManager("sqlite:///test_email.db")
        db_manager.create_tables()
        print("✅ Database connection successful")

        # Create test data
        print("Creating test screener data...")

        execution_id = db_manager.start_agent_execution(
            user_prompt="Test email functionality",
            execution_type="email_test"
        )
        print(f"✅ Created execution: {execution_id}")

        input_id = db_manager.save_screener_input(
            execution_id=execution_id,
            columns=["name", "close", "change"],
            filters=[],
            sort_column="change",
            reasoning="Test email configuration"
        )
        print(f"✅ Created screener input: {input_id}")

        test_result_data = [
            {"name": "AAPL", "close": 150.00, "change": 2.5, "volume": 50000000, "market_cap_basic": 2500000000000},
            {"name": "GOOGL", "close": 2800.00, "change": 1.8, "volume": 25000000, "market_cap_basic": 1800000000000},
            {"name": "MSFT", "close": 350.00, "change": 3.2, "volume": 35000000, "market_cap_basic": 2600000000000}
        ]

        result_id = db_manager.save_screener_result(
            input_id=input_id,
            total_results=3,
            returned_results=3,
            result_data=test_result_data,
            success=True
        )
        print(f"✅ Created screener result: {result_id}")

        # Test email agent integration
        print("Testing email agent with database...")
        from tools.email_agent import EmailAgent

        smtp_config = {
            'smtp_server': os.getenv('SMTP_SERVER', 'smtp.gmail.com'),
            'smtp_port': int(os.getenv('SMTP_PORT', '587')),
            'sender_email': os.getenv('SENDER_EMAIL'),
            'sender_password': os.getenv('SENDER_PASSWORD'),
            'sender_name': os.getenv('SENDER_NAME', 'Test System')
        }

        email_agent = EmailAgent(db_manager=db_manager, smtp_config=smtp_config)
        print("✅ Email agent created successfully")

        # Get recipient emails
        recipient_emails_str = os.getenv('RECIPIENT_EMAILS')
        if recipient_emails_str:
            recipient_emails = [email.strip() for email in recipient_emails_str.split(',')]

            print(f"Sending test report to: {recipient_emails}")

            result_json = email_agent._run(
                recipient_emails=recipient_emails,
                screener_result_id=result_id,
                subject_prefix="DATABASE TEST - TradingView Screener",
                custom_message="This is a test email with real database integration. The screening results are from test data."
            )

            result = json.loads(result_json)

            if result['success']:
                print("✅ DATABASE EMAIL TEST SUCCESSFUL!")
                print(f"   Sent to: {len(recipient_emails)} recipients")
                print(f"   Stocks included: {result['stocks_sent']}")
                return True
            else:
                print(f"❌ DATABASE EMAIL FAILED: {result.get('error')}")
                return False
        else:
            print("⚠️  No RECIPIENT_EMAILS set - skipping actual send")
            print("✅ Database integration test successful (no email sent)")
            return True

    except Exception as e:
        print(f"❌ DATABASE INTEGRATION FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def show_configuration():
    """Show current configuration"""
    print("=" * 50)
    print("CURRENT CONFIGURATION")
    print("=" * 50)

    config_items = [
        ('SENDER_EMAIL', os.getenv('SENDER_EMAIL', '(not set)')),
        ('SENDER_PASSWORD', '(set)' if os.getenv('SENDER_PASSWORD') else '(not set)'),
        ('RECIPIENT_EMAILS', os.getenv('RECIPIENT_EMAILS', '(not set)')),
        ('SMTP_SERVER', os.getenv('SMTP_SERVER', 'smtp.gmail.com')),
        ('SMTP_PORT', os.getenv('SMTP_PORT', '587')),
        ('SENDER_NAME', os.getenv('SENDER_NAME', 'TradingView Screener Agent'))
    ]

    for key, value in config_items:
        status = "✅" if value != "(not set)" else "❌"
        print(f"{status} {key}: {value}")

    print("\nTo configure, create a .env file with:")
    print("SENDER_EMAIL=your-email@gmail.com")
    print("SENDER_PASSWORD=your-app-password")
    print("RECIPIENT_EMAILS=recipient@email.com")


def main():
    """Run all email tests"""

    print("🧪 MINIMAL EMAIL TEST SUITE")
    print("=" * 50)

    # Show configuration first
    show_configuration()

    # Check if basic config is present
    if not os.getenv('SENDER_EMAIL') or not os.getenv('SENDER_PASSWORD'):
        print("\n❌ MISSING EMAIL CONFIGURATION")
        print("Please set SENDER_EMAIL and SENDER_PASSWORD in .env file")
        return False

    # Run tests
    tests = [
        ("SMTP Connection", test_smtp_connection),
        ("Basic Email", test_basic_email),
        ("HTML Email", test_html_email),
        ("Database Integration", test_database_integration)
    ]

    results = []

    for test_name, test_func in tests:
        print(f"\n🧪 Running {test_name} test...")
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name} test crashed: {e}")
            results.append((test_name, False))

    # Summary
    print("\n" + "=" * 50)
    print("TEST SUMMARY")
    print("=" * 50)

    passed = 0
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} {test_name}")
        if result:
            passed += 1

    print(f"\nOverall: {passed}/{len(results)} tests passed")

    if passed == len(results):
        print("🎉 ALL EMAIL TESTS PASSED!")
        print("Email functionality is working correctly.")
    else:
        print("⚠️  Some tests failed. Check the errors above.")

    return passed == len(results)


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)