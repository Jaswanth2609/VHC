#!/usr/bin/env python3

import os
import sys
import json
import time
import argparse
import datetime
import schedule
import subprocess
from utils.weather import get_weather_data, calculate_weather_factor
from utils.notifications import send_notification
from utils.storage import load_user_data, save_user_data

# Default configuration
DEFAULT_CONFIG = {
    "daily_goal": 2.0,  # 2 liters
    "working_hours": {
        "start": "09:00",
        "end": "17:00"
    },
    "custom_intervals": [],  # Empty means automatic distribution
    "activity_level": "moderate",  # low, moderate, high
    "location": "London,UK",
    "api_key": os.getenv("OPENWEATHERMAP_API_KEY", ""),
    "progress": 0.0,
    "last_update": None
}

def parse_time(time_str):
    """Parse time string in format HH:MM"""
    try:
        hours, minutes = map(int, time_str.split(':'))
        if 0 <= hours <= 23 and 0 <= minutes <= 59:
            return hours, minutes
        else:
            raise ValueError("Hours must be 0-23, minutes must be 0-59")
    except:
        raise ValueError("Time must be in format HH:MM")

def time_to_minutes(time_str):
    """Convert time string to minutes since midnight"""
    hours, minutes = parse_time(time_str)
    return hours * 60 + minutes

def minutes_to_time(minutes):
    """Convert minutes since midnight to time string"""
    hours = minutes // 60
    mins = minutes % 60
    return f"{hours:02d}:{mins:02d}"

def generate_intervals(config):
    """Generate notification intervals based on working hours"""
    start_minutes = time_to_minutes(config["working_hours"]["start"])
    end_minutes = time_to_minutes(config["working_hours"]["end"])
    
    # Determine how many glasses of water (roughly 250ml each)
    # the user should drink during working hours
    daily_goal_ml = config["daily_goal"] * 1000
    glasses_per_day = daily_goal_ml / 250
    
    # Assume 70% of water intake happens during working hours
    work_hours_glasses = int(glasses_per_day * 0.7)
    
    if work_hours_glasses < 1:
        work_hours_glasses = 1
    
    # Distribute the glasses evenly throughout working hours
    working_minutes = end_minutes - start_minutes
    interval = working_minutes / (work_hours_glasses + 1)
    
    intervals = []
    for i in range(1, work_hours_glasses + 1):
        minute = start_minutes + (interval * i)
        intervals.append(minutes_to_time(int(minute)))
    
    return intervals

def log_water_intake(amount, config):
    """Log water intake and update progress"""
    config["progress"] += amount
    config["last_update"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    save_user_data(config)
    
    print(f"Logged {amount:.2f} liters of water.")
    print(f"Progress: {config['progress']:.2f}/{config['daily_goal']:.2f} liters "
          f"({config['progress']/config['daily_goal']*100:.1f}%)")

def check_reset_progress(config):
    """Check if we need to reset progress for a new day"""
    if config["last_update"] is None:
        return
    
    last_update = datetime.datetime.strptime(config["last_update"], "%Y-%m-%d %H:%M:%S")
    now = datetime.datetime.now()
    
    # If it's a new day, reset progress
    if last_update.date() < now.date():
        print("New day detected, resetting progress.")
        config["progress"] = 0.0
        save_user_data(config)

def calculate_recommended_amount(config):
    """Calculate the recommended amount of water based on weather and activity"""
    # Base amount for a single notification (in liters)
    base_amount = 0.25  # 250ml as a standard glass
    
    # Activity factor
    activity_factors = {
        "low": 0.8,
        "moderate": 1.0,
        "high": 1.2
    }
    
    activity_factor = activity_factors.get(config["activity_level"], 1.0)
    
    # Weather factor
    try:
        weather_data = get_weather_data(config["location"], config["api_key"])
        weather_factor = calculate_weather_factor(weather_data)
    except Exception as e:
        print(f"Failed to get weather data: {e}")
        weather_factor = 1.0
    
    # Calculate the recommended amount
    recommended_amount = base_amount * activity_factor * weather_factor
    
    return round(recommended_amount, 2)

def notify_drink_water(config):
    """Send a notification to drink water"""
    recommended_amount = calculate_recommended_amount(config)
    
    progress_percent = (config["progress"] / config["daily_goal"]) * 100
    remaining = config["daily_goal"] - config["progress"]
    
    message = (f"Time to drink water! Recommended: {recommended_amount:.2f}L\n"
               f"Progress: {config['progress']:.2f}/{config['daily_goal']:.2f}L "
               f"({progress_percent:.1f}%)\n"
               f"Remaining: {remaining:.2f}L")
    
    send_notification("Hydration Coach", message)
    
    return recommended_amount

def setup_schedule(config):
    """Set up the notification schedule"""
    # Clear existing schedule
    schedule.clear()
    
    # Determine notification times
    if config["custom_intervals"] and len(config["custom_intervals"]) > 0:
        notification_times = config["custom_intervals"]
    else:
        notification_times = generate_intervals(config)
        # Save the generated intervals back to config
        config["custom_intervals"] = notification_times
        save_user_data(config)
    
    print("Notification times:")
    for time_str in notification_times:
        print(f"  - {time_str}")
        schedule.every().day.at(time_str).do(notify_drink_water, config)
    
    # Schedule a midnight job to reset progress
    schedule.every().day.at("00:00").do(lambda: setattr(config, "progress", 0.0) or save_user_data(config))

def configure(args, config):
    """Configure the application based on command-line arguments"""
    modified = False
    
    if args.daily_goal is not None:
        config["daily_goal"] = args.daily_goal
        modified = True
    
    if args.start_time is not None:
        # Validate time format
        parse_time(args.start_time)
        config["working_hours"]["start"] = args.start_time
        modified = True
    
    if args.end_time is not None:
        # Validate time format
        parse_time(args.end_time)
        config["working_hours"]["end"] = args.end_time
        modified = True
    
    if args.activity_level is not None:
        if args.activity_level not in ["low", "moderate", "high"]:
            print("Activity level must be one of: low, moderate, high")
            sys.exit(1)
        config["activity_level"] = args.activity_level
        modified = True
    
    if args.location is not None:
        config["location"] = args.location
        modified = True
    
    if args.api_key is not None:
        config["api_key"] = args.api_key
        modified = True
    
    if args.intervals is not None:
        # Parse intervals
        try:
            times = args.intervals.split(',')
            for time_str in times:
                parse_time(time_str.strip())
            config["custom_intervals"] = [t.strip() for t in times]
        except ValueError as e:
            print(f"Invalid time format: {e}")
            sys.exit(1)
        modified = True
    
    if args.auto_intervals:
        config["custom_intervals"] = []
        modified = True
    
    if modified:
        save_user_data(config)
        print("Configuration updated successfully.")
    
    return config

def display_status(config):
    """Display the current status"""
    print("\n===== Hydration Coach Status =====")
    print(f"Daily Goal: {config['daily_goal']} liters")
    print(f"Activity Level: {config['activity_level']}")
    print(f"Working Hours: {config['working_hours']['start']} - {config['working_hours']['end']}")
    print(f"Location: {config['location']}")
    
    if config["custom_intervals"] and len(config["custom_intervals"]) > 0:
        print(f"Notification Intervals: {', '.join(config['custom_intervals'])}")
    else:
        intervals = generate_intervals(config)
        print(f"Notification Intervals (auto): {', '.join(intervals)}")
    
    try:
        weather_data = get_weather_data(config["location"], config["api_key"])
        temp = weather_data.get("main", {}).get("temp", 0) - 273.15  # Convert from Kelvin to Celsius
        condition = weather_data.get("weather", [{}])[0].get("main", "Unknown")
        
        print(f"\nCurrent Weather: {condition}, {temp:.1f}°C")
        
        weather_factor = calculate_weather_factor(weather_data)
        print(f"Weather Hydration Factor: {weather_factor:.2f}x")
    except Exception as e:
        print(f"\nWeather Data: Unavailable ({e})")
    
    print(f"\nProgress: {config['progress']:.2f}/{config['daily_goal']:.2f} liters "
          f"({config['progress']/config['daily_goal']*100:.1f}%)")
    
    if config["last_update"]:
        print(f"Last Update: {config['last_update']}")
    
    print("================================\n")

def main():
    """Main function"""
    parser = argparse.ArgumentParser(description="Virtual Hydration Coach")
    
    # Create subparsers for commands
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # Configure parser
    configure_parser = subparsers.add_parser("configure", help="Configure the application")
    configure_parser.add_argument("--daily-goal", type=float, help="Daily water intake goal in liters")
    configure_parser.add_argument("--start-time", help="Working hours start time (HH:MM)")
    configure_parser.add_argument("--end-time", help="Working hours end time (HH:MM)")
    configure_parser.add_argument("--activity-level", choices=["low", "moderate", "high"], 
                                 help="Your activity level")
    configure_parser.add_argument("--location", help="Your location (city,country)")
    configure_parser.add_argument("--api-key", help="OpenWeatherMap API key")
    configure_parser.add_argument("--intervals", help="Custom notification intervals (comma-separated times)")
    configure_parser.add_argument("--auto-intervals", action="store_true", 
                                 help="Generate intervals automatically based on working hours")
    
    # Log water intake parser
    log_parser = subparsers.add_parser("log", help="Log water intake")
    log_parser.add_argument("amount", type=float, help="Amount of water in liters")
    
    # Status parser
    status_parser = subparsers.add_parser("status", help="Show current status")
    
    # Run parser
    run_parser = subparsers.add_parser("run", help="Run the hydration coach")
    
    # Parse arguments
    args = parser.parse_args()
    
    # Load configuration
    config = load_user_data()
    if not config:
        config = DEFAULT_CONFIG
        save_user_data(config)
    
    # Check if we need to reset progress for a new day
    check_reset_progress(config)
    
    # Handle commands
    if args.command == "configure":
        config = configure(args, config)
    elif args.command == "log":
        log_water_intake(args.amount, config)
    elif args.command == "status":
        display_status(config)
    elif args.command == "run":
        # Check if API key is available
        if not config["api_key"]:
            print("Error: OpenWeatherMap API key is not set.")
            print("Please set it using: hydration_coach configure --api-key YOUR_API_KEY")
            print("You can get a free API key from https://openweathermap.org/")
            sys.exit(1)
        
        # Set up the notification schedule
        setup_schedule(config)
        
        print("Hydration Coach is running. Press Ctrl+C to stop.")
        
        try:
            while True:
                schedule.run_pending()
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nHydration Coach stopped.")
    else:
        # If no command is provided, show help
        parser.print_help()

if __name__ == "__main__":
    main()
