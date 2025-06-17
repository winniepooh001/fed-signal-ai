# setup_email.py
"""
Email setup and testing script for the screener system
"""

import os
import sys
from typing import Dict, List
from dotenv import load_dotenv, set_key
import json


def check_email_config() -> Dict[str, str]:
    """Check current email configuration"""

    load_dotenv()

    config = {
        'SENDER_EMAIL': os.getenv('SENDER_EMAIL', ''),
        'SENDER_PASSWORD': os.getenv('SENDER_PASSWORD', ''),
        'RECIPIENT_EMAILS': os.getenv('RECIPIENT_EMAILS', ''),
        'SMTP_SERVER': os.getenv('SMTP_SERVER', 'smtp.gmail.com'),
        'SMTP_PORT': os.getenv('SMTP_PORT', '587'),
        'SENDER_NAME': os.getenv('SENDER_NAME', 'TradingView Screener Agent')
    }

    return config


def interactive_email_setup():
    """Interactive setup for email configuration"""

    print("\n" + "=" * 60)
    print("📧 EMAIL CONFIGURATION SETUP")
    print("=" * 60)

    # Load existing config
    config = check_email_config()

    print("\nCurrent configuration:")
    for key, value in config.items():
        if 'PASSWORD' in key and value:
            display_value = '*' * len(value)
        else:
            display_value = value or '(not set)'
        print(f"  {key}: {display_value}")

    print("\n" + "-" * 40)
    print("SETUP EMAIL CONFIGURATION")
    print("-" * 40)

    # Get sender email
    sender_email = input(f"\nSender email [{config['SENDER_EMAIL']}]: ").strip()
    if sender_email:
        config['SENDER_EMAIL'] = sender_email

    # Get sender password
    print("\nFor Gmail, use an App Password (not your regular password)")
    print("Guide: https://support.google.com/accounts/answer/185833")
    sender_password = input(f"Sender password/app password: ").strip()
    if sender_password:
        config['SENDER_PASSWORD'] = sender_password

    # Get recipient emails
    print("\nEnter recipient emails (comma-separated)")
    recipient_emails = input(f"Recipients [{config['RECIPIENT_EMAILS']}]: ").strip()
    if recipient_emails:
        config['RECIPIENT_EMAILS'] = recipient_emails

    # Get sender name
    sender_name = input(f"\nSender name [{config['SENDER_NAME']}]: ").strip()
    if sender_name:
        config['SENDER_NAME'] = sender_name

    # SMTP settings (usually don't need to change for Gmail)
    print(f"\nSMTP Server: {config['SMTP_SERVER']}")
    print(f"SMTP Port: {config['SMTP_PORT']}")
    change_smtp = input("Change SMTP settings? (y/N): ").strip().lower()

    if change_smtp == 'y':
        smtp_server = input(f"SMTP Server [{config['SMTP_SERVER']}]: ").strip()
        if smtp_server:
            config['SMTP_SERVER'] = smtp_server

        smtp_port = input(f"SMTP Port [{config['SMTP_PORT']}]: ").strip()
        if smtp_port:
            config['SMTP_PORT'] = smtp_port

    # Save to .env file
    print("\n" + "-" * 40)
    print("SAVING CONFIGURATION")
    print("-" * 40)

    env_file = '.env'

    for key, value in config.items():
        if value:  # Only save non-empty values
            set_key(env_file, key, value)
            print(f"✅ Saved {key}")

    print(f"\n✅ Configuration saved to {env_file}")

    return config


def test_email_config():
    """Test email configuration by sending a test email"""

    print("\n" + "=" * 60)
    print("🧪 TESTING EMAIL CONFIGURATION")
    print("=" * 60)

    try:
        # Import after setup to ensure environment is loaded
        from tools.email_agent import EmailAgent
        from database import DatabaseManager
        import smtplib

        config = check_email_config()

        # Check required fields
        required_fields = ['SENDER_EMAIL', 'SENDER_PASSWORD']
        missing_fields = [field for field in required_fields if not config[field]]

        if missing_fields:
            print(f"❌ Missing required fields: {', '.join(missing_fields)}")
            print("Run setup first: python setup_email.py --setup")
            return False

        # Test SMTP connection
        print("Testing SMTP connection...")

        smtp_config = {
            'smtp_server': config['SMTP_SERVER'],
            'smtp_port': int(config['SMTP_PORT']),
            'sender_email': config['SENDER_EMAIL'],
            'sender_password': config['SENDER_PASSWORD'],
            'sender_name': config['SENDER_NAME']
        }

        try:
            with smtplib.SMTP(smtp_config['smtp_server'], smtp_config['smtp_port']) as server:
                server.starttls()
                server.login(smtp_config['sender_email'], smtp_config['sender_password'])
                print("✅ SMTP connection successful")

        except Exception as e:
            print(f"❌ SMTP connection failed: {e}")
            return False

        # Test with actual email (if recipients configured)
        if config['RECIPIENT_EMAILS']:
            send_test = input("\nSend test email? (y/N): ").strip().lower()

            if send_test == 'y':
                print("Sending test email...")

                # Create a dummy screener result for testing
                db_manager = DatabaseManager("sqlite:///screener_data.db")
                db_manager.create_tables()

                # Create test data
                test_execution_id = db_manager.start_agent_execution(
                    user_prompt="Test email functionality",
                    execution_type="email_test"
                )

                test_input_id = db_manager.save_screener_input(
                    execution_id=test_execution_id,
                    columns=["name", "close", "change"],
                    filters=[],
                    sort_column="change",
                    reasoning="Test email configuration"
                )

                test_result_data = [
                    {"name": "TEST STOCK", "close": 100.00, "change": 5.0, "volume": 1000000,
                     "market_cap_basic": 1000000000}
                ]

                test_result_id = db_manager.save_screener_result(
                    input_id=test_input_id,
                    total_results=1,
                    returned_results=1,
                    result_data=test_result_data,
                    success=True
                )

                # Send test email
                email_agent = EmailAgent(db_manager=db_manager, smtp_config=smtp_config)

                recipient_emails = [email.strip() for email in config['RECIPIENT_EMAILS'].split(',')]

                result_json = email_agent._run(
                    recipient_emails=recipient_emails,
                    screener_result_id=test_result_id,
                    subject_prefix="TEST - TradingView Screener",
                    custom_message="This is a test email to verify the screener email functionality is working correctly."
                )

                result = json.loads(result_json)

                if result['success']:
                    print("✅ Test email sent successfully!")
                    print(f"Recipients: {', '.join(recipient_emails)}")
                else:
                    print(f"❌ Test email failed: {result.get('error')}")
                    return False

        print("\n✅ Email configuration test completed successfully!")
        return True

    except Exception as e:
        print(f"❌ Email test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def show_current_config():
    """Display current email configuration"""

    print("\n" + "=" * 60)
    print("📋 CURRENT EMAIL CONFIGURATION")
    print("=" * 60)

    config = check_email_config()

    for key, value in config.items():
        if 'PASSWORD' in key and value:
            display_value = f"{'*' * min(len(value), 8)} (set)"
        elif value:
            display_value = value
        else:
            display_value = "(not configured)"

        status = "✅" if value else "❌"
        print(f"{status} {key}: {display_value}")

    # Check if configuration is complete
    required_fields = ['SENDER_EMAIL', 'SENDER_PASSWORD']
    complete = all(config[field] for field in required_fields)

    print("\n" + "-" * 60)
    if complete:
        print("✅ Email configuration is complete")

        if config['RECIPIENT_EMAILS']:
            recipients = config['RECIPIENT_EMAILS'].split(',')
            print(f"📧 Will send to {len(recipients)} recipient(s)")
        else:
            print("⚠️  No recipients configured - emails won't be sent")
    else:
        print("❌ Email configuration is incomplete")
        missing = [field for field in required_fields if not config[field]]
        print(f"Missing: {', '.join(missing)}")


def main():
    """Main function for email setup script"""

    if len(sys.argv) > 1:
        command = sys.argv[1]

        if command == '--setup' or command == '-s':
            interactive_email_setup()
        elif command == '--test' or command == '-t':
            test_email_config()
        elif command == '--show' or command == '--config':
            show_current_config()
        else:
            print(f"Unknown command: {command}")
            print("Usage: python setup_email.py [--setup|--test|--show]")
    else:
        # Interactive menu
        print("\n📧 EMAIL SETUP UTILITY")
        print("=" * 30)
        print("1. Setup email configuration")
        print("2. Test email configuration")
        print("3. Show current configuration")
        print("4. Exit")

        while True:
            try:
                choice = input("\nSelect option (1-4): ").strip()

                if choice == '1':
                    interactive_email_setup()
                elif choice == '2':
                    test_email_config()
                elif choice == '3':
                    show_current_config()
                elif choice == '4':
                    print("Goodbye!")
                    break
                else:
                    print("Invalid choice. Please select 1-4.")

            except KeyboardInterrupt:
                print("\nGoodbye!")
                break
            except Exception as e:
                print(f"Error: {e}")


if __name__ == "__main__":
    main()