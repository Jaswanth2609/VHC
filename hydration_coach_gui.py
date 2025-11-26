#!/usr/bin/env python3

import os
import sys
import json
import time
import datetime
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import threading
import schedule
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from ttkthemes import ThemedTk
from PIL import Image, ImageTk
import webbrowser

# Import utilities from the original hydration coach
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
    "last_update": None,
    "notification_enabled": True,
    "notification_sound": True,
    "notification_style": "standard",  # standard, minimal, detailed
    "theme": "arc",  # Default theme
    "color_scheme": "blue",  # Default color scheme
    "history": {}  # Store daily progress history
}

# Color schemes
COLOR_SCHEMES = {
    "blue": {
        "primary": "#1976D2",
        "secondary": "#2196F3",
        "accent": "#BBDEFB",
        "text": "#212121",
        "text_light": "#FFFFFF"
    },
    "teal": {
        "primary": "#00796B",
        "secondary": "#009688",
        "accent": "#B2DFDB",
        "text": "#212121",
        "text_light": "#FFFFFF"
    },
    "purple": {
        "primary": "#512DA8",
        "secondary": "#673AB7",
        "accent": "#D1C4E9",
        "text": "#212121",
        "text_light": "#FFFFFF"
    },
    "orange": {
        "primary": "#E64A19",
        "secondary": "#FF5722",
        "accent": "#FFCCBC",
        "text": "#212121",
        "text_light": "#FFFFFF"
    },
    "green": {
        "primary": "#388E3C",
        "secondary": "#4CAF50",
        "accent": "#C8E6C9",
        "text": "#212121",
        "text_light": "#FFFFFF"
    }
}

# Available themes for ttkthemes
AVAILABLE_THEMES = [
    "arc", "breeze", "equilux", "plastik", 
    "yaru", "black", "clearlooks", "elegance", 
    "radiance", "ubuntu", "scidblue", "scidgreen",
    "scidgrey", "scidmint", "scidpink", "scidpurple",
    "scidsand", "smog", "winxpblue"
]

# Functions imported from original application
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

def check_reset_progress(config):
    """Check if we need to reset progress for a new day and store history"""
    if config["last_update"] is None:
        return
    
    last_update = datetime.datetime.strptime(config["last_update"], "%Y-%m-%d %H:%M:%S")
    now = datetime.datetime.now()
    
    # If it's a new day, reset progress and store history
    if last_update.date() < now.date():
        # Store yesterday's progress in history
        yesterday = last_update.strftime("%Y-%m-%d")
        if "history" not in config:
            config["history"] = {}
        config["history"][yesterday] = config["progress"]
        
        # Reset progress for new day
        config["progress"] = 0.0
        save_user_data(config)
        return True
    return False

class CircularProgressBar(tk.Canvas):
    """Custom circular progress bar widget with enhanced visual appearance"""
    def __init__(self, parent, size=200, width=20, progress=0.0, fg_color="#2196F3", bg_color="#BBDEFB", text_color="#212121", **kwargs):
        super().__init__(parent, width=size, height=size, highlightthickness=0, **kwargs)
        self.size = size
        self.width = width
        self.progress = float(progress)  # Ensure progress is float
        self.fg_color = fg_color
        self.bg_color = bg_color
        self.text_color = text_color
        self.draw()
    
    def draw(self):
        """Draw the progress bar with enhanced visual elements"""
        self.delete("progress")
        padding = self.width / 2
        center = self.size / 2
        radius = (self.size - self.width) / 2
        
        # Draw shadow effect for depth
        shadow_padding = padding + 1
        self.create_oval(
            shadow_padding, shadow_padding, 
            self.size - shadow_padding, self.size - shadow_padding, 
            width=self.width, outline="#CCCCCC", tags="progress"
        )
        
        # Draw background circle
        self.create_oval(
            padding, padding, 
            self.size - padding, self.size - padding, 
            width=self.width, outline=self.bg_color, tags="progress"
        )
        
        # Draw progress arc
        start_angle = 90
        extent = -self.progress * 360
        self.create_arc(
            padding, padding, 
            self.size - padding, self.size - padding, 
            start=start_angle, extent=extent, 
            width=self.width, outline=self.fg_color, 
            style=tk.ARC, tags="progress"
        )
        
        # Draw goal marker at 100%
        marker_size = 3
        self.create_oval(
            center, padding - marker_size,
            center + marker_size * 2, padding + marker_size,
            fill="#212121", outline="", tags="progress"
        )
        
        # Draw percentage text in the middle
        percentage = int(self.progress * 100)
        self.create_text(
            center, center - 10, 
            text=f"{percentage}%", 
            font=("Arial", int(self.size / 10), "bold"), 
            fill=self.text_color, tags="progress"
        )
        
        # Draw label below percentage
        self.create_text(
            center, center + 15, 
            text="of daily goal", 
            font=("Arial", int(self.size / 16)), 
            fill=self.text_color, tags="progress"
        )
        
    def set_progress(self, progress):
        """Set the progress value (0.0 to 1.0)"""
        self.progress = max(0.0, min(1.0, float(progress)))
        self.draw()
        
    def animate_to(self, target_progress, duration=500, steps=20):
        """Animate progress bar to a target value"""
        if not hasattr(self, '_after_id'):
            self._after_id = None
            
        # Cancel any ongoing animation
        if self._after_id:
            self.after_cancel(self._after_id)
            self._after_id = None
            
        start_progress = self.progress
        progress_diff = target_progress - start_progress
        step_time = int(duration / steps)
        
        def animate_step(current_step):
            if current_step >= steps:
                self.set_progress(target_progress)
                self._after_id = None
                return
                
            progress = start_progress + (progress_diff * (current_step / steps))
            self.set_progress(progress)
            self._after_id = self.after(step_time, lambda: animate_step(current_step + 1))
            
        animate_step(0)

class NotificationWindow(tk.Toplevel):
    """Custom notification window for hydration reminders"""
    def __init__(self, parent, title, message, style="standard", sound=True, on_drink_callback=None):
        super().__init__(parent)
        self.parent = parent
        self.title(title)
        self.geometry("400x250")
        self.minsize(350, 200)
        
        # Remove standard window decorations for modern look
        self.overrideredirect(True)
        
        # Set window to always stay on top
        self.attributes("-topmost", True)
        
        # Calculate position (bottom right of the screen)
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        window_width = 400
        window_height = 250
        position_x = screen_width - window_width - 20
        position_y = screen_height - window_height - 40
        self.geometry(f"{window_width}x{window_height}+{position_x}+{position_y}")
        
        # Configure window appearance
        self.configure(bg="#FFFFFF")
        
        # Add border
        self.frame = ttk.Frame(self, padding=2)
        self.frame.pack(fill=tk.BOTH, expand=True)
        
        # Notification header
        header_frame = ttk.Frame(self.frame)
        header_frame.pack(fill=tk.X, padx=10, pady=(10, 5))
        
        # Icon - water droplet
        self.drop_icon = ttk.Label(header_frame, text="💧", font=("Arial", 24))
        self.drop_icon.pack(side=tk.LEFT, padx=(0, 10))
        
        # Title
        ttk.Label(header_frame, text=title, font=("Arial", 14, "bold")).pack(side=tk.LEFT)
        
        # Close button
        close_btn = ttk.Button(header_frame, text="×", width=3, command=self.destroy)
        close_btn.pack(side=tk.RIGHT)
        
        # Message content
        message_frame = ttk.Frame(self.frame, padding=10)
        message_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        message_text = tk.Text(message_frame, wrap=tk.WORD, height=4, 
                             font=("Arial", 11), bd=0, highlightthickness=0)
        message_text.insert(tk.END, message)
        message_text.config(state=tk.DISABLED)
        message_text.pack(fill=tk.BOTH, expand=True)
        
        # Action buttons
        button_frame = ttk.Frame(self.frame)
        button_frame.pack(fill=tk.X, padx=10, pady=10)
        
        # Callback function for when user confirms they drank water
        self.on_drink_callback = on_drink_callback
        
        # "I'll drink later" button
        later_btn = ttk.Button(button_frame, text="Remind me later", 
                               command=self.remind_later)
        later_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        # "I drank it" button
        drink_btn = ttk.Button(button_frame, text="I drank it!", 
                               command=self.on_drink_water, style="Accent.TButton")
        drink_btn.pack(side=tk.RIGHT)
        
        # Close window automatically after 60 seconds
        self.after(60000, self.destroy)
        
        # Play sound if enabled
        if sound:
            try:
                # Simple console bell for sound notification
                self.bell()
            except:
                pass
    
    def remind_later(self):
        """Handle remind later action"""
        # Schedule a new notification in 15 minutes
        self.after(15 * 60 * 1000, lambda: self.parent.notify_drink_water())
        self.destroy()
    
    def on_drink_water(self):
        """Handle user confirmation of drinking water"""
        if self.on_drink_callback:
            self.on_drink_callback()
        self.destroy()

class HydrationCoachApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Hydration Coach")
        self.root.minsize(800, 600)
        self.root.geometry("900x650")
        
        # Load configuration
        self.config = load_user_data()
        if not self.config:
            self.config = DEFAULT_CONFIG
            save_user_data(self.config)
        
        # Update config with any missing keys from DEFAULT_CONFIG
        for key, value in DEFAULT_CONFIG.items():
            if key not in self.config:
                self.config[key] = value
        
        # Save the updated config
        save_user_data(self.config)
        
        # Initialize theme
        self.theme = self.config.get("theme", "arc")
        self.color_scheme = self.config.get("color_scheme", "blue")
        
        # Apply theme to the window if it's a ThemedTk instance
        if isinstance(self.root, ThemedTk):
            if self.theme in AVAILABLE_THEMES:
                self.root.set_theme(self.theme)
        
        # Set color scheme
        self.colors = COLOR_SCHEMES[self.color_scheme]
        
        # Create custom styles
        self.style = ttk.Style()
        self.apply_styles()
        
        # Check if progress needs to be reset for a new day
        self.reset_detected = check_reset_progress(self.config)
        
        # Initialize the scheduler in a separate thread
        self.scheduler_thread = None
        self.scheduler_running = False
        
        # Setup main container
        self.setup_ui()
        
        # Start the scheduler if notifications are enabled
        if self.config["notification_enabled"]:
            self.start_scheduler()
        
        # Bind close event to save configuration
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
    
    def apply_styles(self):
        """Apply custom styles based on color scheme"""
        # Configure button styles
        self.style.configure("TButton", font=("Arial", 10), padding=6)
        self.style.configure("Accent.TButton", 
                           background=self.colors["primary"],
                           foreground="#212121",  # Dark text for better visibility
                           font=("Arial", 10, "bold"))
        self.style.configure("Reset.TButton", 
                           background="#e57373",  # Light red color
                           foreground="#212121",  # Dark text (almost black)
                           font=("Arial", 10, "bold"))
        
        # Hover effect for buttons (if supported by theme)
        try:
            self.style.map("TButton", 
                         background=[("active", self.colors["secondary"])],
                         foreground=[("active", self.colors["text_light"])])
            self.style.map("Accent.TButton",
                         background=[("active", self.colors["secondary"])])
        except:
            pass
        
        # Configure label styles with improved fonts
        self.style.configure("TLabel", font=("Arial", 11))
        self.style.configure("Header.TLabel", font=("Arial", 18, "bold"))
        self.style.configure("Subheader.TLabel", font=("Arial", 14, "bold"))
        self.style.configure("Stats.TLabel", font=("Arial", 12), foreground=self.colors["text"])
        self.style.configure("Value.TLabel", font=("Arial", 12, "bold"), foreground=self.colors["primary"])
        
        # Configure frame styles with subtle shadow effect
        self.style.configure("Card.TFrame", background="#FFFFFF", relief="ridge", borderwidth=1)
        
        # Configure notebook style with better contrast
        self.style.configure("TNotebook", background="#F5F5F5")
        self.style.configure("TNotebook.Tab", font=("Arial", 11), padding=[12, 8])
        
        # Special button styles
        self.style.configure("Reset.TButton", 
                           background="#F44336", 
                           foreground="#212121",  # Dark text (almost black)
                           font=("Arial", 10))
    
    def setup_ui(self):
        """Set up the main user interface"""
        # Create main container
        main_container = ttk.Frame(self.root, padding=10)
        main_container.pack(fill=tk.BOTH, expand=True)
        
        # Create and pack the notebook (tab control)
        self.notebook = ttk.Notebook(main_container)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Create the tabs
        self.dashboard_tab = ttk.Frame(self.notebook, padding=10)
        self.settings_tab = ttk.Frame(self.notebook, padding=10)
        self.history_tab = ttk.Frame(self.notebook, padding=10)
        self.about_tab = ttk.Frame(self.notebook, padding=10)
        
        # Add tabs to the notebook
        self.notebook.add(self.dashboard_tab, text="Dashboard")
        self.notebook.add(self.settings_tab, text="Settings")
        self.notebook.add(self.history_tab, text="History")
        self.notebook.add(self.about_tab, text="About")
        
        # Setup each tab content
        self.setup_dashboard_tab()
        self.setup_settings_tab()
        self.setup_history_tab()
        self.setup_about_tab()
        
        # Show reset notification if needed
        if self.reset_detected:
            messagebox.showinfo("Daily Reset", 
                               "A new day has begun! Your progress has been reset.")
    
    def setup_dashboard_tab(self):
        """Set up the dashboard tab"""
        # Header
        header_frame = ttk.Frame(self.dashboard_tab)
        header_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(header_frame, text="Hydration Dashboard", style="Header.TLabel").pack(side=tk.LEFT)
        
        refresh_btn = ttk.Button(header_frame, text="Refresh", command=self.refresh_dashboard)
        refresh_btn.pack(side=tk.RIGHT)
        
        # Main content - split into two columns
        content_frame = ttk.Frame(self.dashboard_tab)
        content_frame.pack(fill=tk.BOTH, expand=True)
        
        # Left column - Progress
        left_col = ttk.Frame(content_frame, padding=10)
        left_col.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Progress card
        progress_card = ttk.Frame(left_col, style="Card.TFrame", padding=15)
        progress_card.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        ttk.Label(progress_card, text="Today's Progress", style="Subheader.TLabel").pack(anchor=tk.W, pady=(0, 10))
        
        # Circular progress bar
        progress_frame = ttk.Frame(progress_card)
        progress_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        
        progress_value = self.config["progress"] / self.config["daily_goal"]
        progress_value = min(1.0, max(0.0, progress_value))  # Ensure between 0 and 1
        
        self.progress_bar = CircularProgressBar(
            progress_frame, 
            size=200, width=20, 
            progress=progress_value,
            fg_color=self.colors["primary"],
            bg_color=self.colors["accent"]
        )
        self.progress_bar.pack(pady=10)
        
        # Progress details
        stats_frame = ttk.Frame(progress_card)
        stats_frame.pack(fill=tk.X, pady=10)
        
        # Current amount
        ttk.Label(stats_frame, text="Current:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.current_label = ttk.Label(stats_frame, text=f"{self.config['progress']:.2f} L")
        self.current_label.grid(row=0, column=1, sticky=tk.W, pady=2, padx=10)
        
        # Goal amount
        ttk.Label(stats_frame, text="Goal:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.goal_label = ttk.Label(stats_frame, text=f"{self.config['daily_goal']:.2f} L")
        self.goal_label.grid(row=1, column=1, sticky=tk.W, pady=2, padx=10)
        
        # Remaining amount
        remaining = max(0, self.config["daily_goal"] - self.config["progress"])
        ttk.Label(stats_frame, text="Remaining:").grid(row=2, column=0, sticky=tk.W, pady=2)
        self.remaining_label = ttk.Label(stats_frame, text=f"{remaining:.2f} L")
        self.remaining_label.grid(row=2, column=1, sticky=tk.W, pady=2, padx=10)
        
        # Log water and action buttons
        self.log_frame = ttk.Frame(progress_card)
        self.log_frame.pack(fill=tk.X, pady=10)
        
        self.log_btn = ttk.Button(self.log_frame, text="Log Water Intake", 
                                 command=self.show_log_dialog, style="Accent.TButton")
        self.log_btn.pack(fill=tk.X, pady=5)
        
        # Action buttons row
        action_frame = ttk.Frame(self.log_frame)
        action_frame.pack(fill=tk.X, pady=5)
        
        # Reset Progress Button
        self.reset_btn = ttk.Button(action_frame, text="Reset Progress", 
                                  command=self.reset_progress, style="Reset.TButton")
        self.reset_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 2))
        
        # Add goal amount button
        self.add_goal_btn = ttk.Button(action_frame, text="Complete Goal", 
                                     command=lambda: self.log_water_intake(
                                         max(0, self.config["daily_goal"] - self.config["progress"])
                                     ))
        self.add_goal_btn.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(2, 0))
        
        # Quick log buttons (common amounts)
        quick_log_frame = ttk.Frame(progress_card)
        quick_log_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(quick_log_frame, text="Quick Add:").pack(anchor=tk.W, pady=(0, 5))
        
        quick_amounts = [0.15, 0.25, 0.33, 0.5, 0.75]
        quick_btn_frame = ttk.Frame(quick_log_frame)
        quick_btn_frame.pack(fill=tk.X)
        
        for i, amount in enumerate(quick_amounts):
            btn = ttk.Button(quick_btn_frame, text=f"{amount:.2f} L", 
                            command=lambda a=amount: self.log_water_intake(a))
            btn.pack(side=tk.LEFT, padx=2, pady=5, fill=tk.X, expand=True)
        
        # Right column - Weather and notifications
        right_col = ttk.Frame(content_frame, padding=10)
        right_col.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        
        # Weather card
        self.weather_card = ttk.Frame(right_col, style="Card.TFrame", padding=15)
        self.weather_card.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(self.weather_card, text="Weather Conditions", style="Subheader.TLabel").pack(anchor=tk.W, pady=(0, 10))
        
        self.weather_frame = ttk.Frame(self.weather_card)
        self.weather_frame.pack(fill=tk.X)
        
        self.location_label = ttk.Label(self.weather_frame, text=f"Location: {self.config['location']}")
        self.location_label.pack(anchor=tk.W, pady=2)
        
        self.weather_status_label = ttk.Label(self.weather_frame, text="Fetching weather data...")
        self.weather_status_label.pack(anchor=tk.W, pady=2)
        
        self.temp_label = ttk.Label(self.weather_frame, text="Temperature: --°C")
        self.temp_label.pack(anchor=tk.W, pady=2)
        
        self.humidity_label = ttk.Label(self.weather_frame, text="Humidity: --%")
        self.humidity_label.pack(anchor=tk.W, pady=2)
        
        self.factor_label = ttk.Label(self.weather_frame, text="Hydration Factor: --")
        self.factor_label.pack(anchor=tk.W, pady=2)
        
        # Notifications card
        notifications_card = ttk.Frame(right_col, style="Card.TFrame", padding=15)
        notifications_card.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        ttk.Label(notifications_card, text="Notification Schedule", style="Subheader.TLabel").pack(anchor=tk.W, pady=(0, 10))
        
        # Working hours info
        work_hours_frame = ttk.Frame(notifications_card)
        work_hours_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(work_hours_frame, text="Working Hours:").pack(side=tk.LEFT)
        self.work_hours_label = ttk.Label(
            work_hours_frame, 
            text=f"{self.config['working_hours']['start']} - {self.config['working_hours']['end']}"
        )
        self.work_hours_label.pack(side=tk.LEFT, padx=5)
        
        # Notification times
        times_frame = ttk.Frame(notifications_card)
        times_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        ttk.Label(times_frame, text="Notification Times:").pack(anchor=tk.W)
        
        # Get times to display
        if self.config["custom_intervals"] and len(self.config["custom_intervals"]) > 0:
            self.notification_times = self.config["custom_intervals"]
        else:
            self.notification_times = generate_intervals(self.config)
            
        # Display times
        times_list_frame = ttk.Frame(times_frame)
        times_list_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        self.times_listbox = tk.Listbox(times_list_frame, height=6)
        self.times_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        times_scrollbar = ttk.Scrollbar(times_list_frame, orient=tk.VERTICAL, command=self.times_listbox.yview)
        times_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.times_listbox.config(yscrollcommand=times_scrollbar.set)
        
        for time_str in self.notification_times:
            self.times_listbox.insert(tk.END, time_str)
        
        # Status bar
        status_bar = ttk.Frame(self.dashboard_tab)
        status_bar.pack(fill=tk.X, pady=(10, 0))
        
        # Last update time
        last_update = self.config.get("last_update", "Never")
        self.status_label = ttk.Label(status_bar, text=f"Last updated: {last_update}")
        self.status_label.pack(side=tk.LEFT)
        
        # Notification status
        notif_status = "Enabled" if self.config["notification_enabled"] else "Disabled"
        self.notif_status_label = ttk.Label(status_bar, text=f"Notifications: {notif_status}")
        self.notif_status_label.pack(side=tk.RIGHT)
        
        # Update weather data
        self.update_weather_info()
    
    def setup_settings_tab(self):
        """Set up the settings tab"""
        # Header
        header_frame = ttk.Frame(self.settings_tab)
        header_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(header_frame, text="Settings", style="Header.TLabel").pack(side=tk.LEFT)
        
        save_btn = ttk.Button(header_frame, text="Save Settings", 
                             command=self.save_settings, style="Accent.TButton")
        save_btn.pack(side=tk.RIGHT)
        
        # Settings container with two columns
        settings_container = ttk.Frame(self.settings_tab)
        settings_container.pack(fill=tk.BOTH, expand=True)
        
        # Left column - User settings
        left_col = ttk.Frame(settings_container, padding=10)
        left_col.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # User settings card
        user_settings = ttk.LabelFrame(left_col, text="User Settings", padding=10)
        user_settings.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Daily Goal
        goal_frame = ttk.Frame(user_settings)
        goal_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(goal_frame, text="Daily Goal (liters):").grid(row=0, column=0, sticky=tk.W, pady=5)
        
        self.goal_var = tk.DoubleVar(value=self.config["daily_goal"])
        goal_entry = ttk.Spinbox(goal_frame, from_=0.5, to=10.0, increment=0.1, 
                                textvariable=self.goal_var, width=10)
        goal_entry.grid(row=0, column=1, pady=5, padx=5)
        
        # Activity Level
        activity_frame = ttk.Frame(user_settings)
        activity_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(activity_frame, text="Activity Level:").grid(row=0, column=0, sticky=tk.W, pady=5)
        
        self.activity_var = tk.StringVar(value=self.config["activity_level"])
        activity_combo = ttk.Combobox(activity_frame, textvariable=self.activity_var, width=15)
        activity_combo["values"] = ("low", "moderate", "high")
        activity_combo["state"] = "readonly"
        activity_combo.grid(row=0, column=1, pady=5, padx=5)
        
        # Location
        location_frame = ttk.Frame(user_settings)
        location_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(location_frame, text="Location:").grid(row=0, column=0, sticky=tk.W, pady=5)
        
        self.location_var = tk.StringVar(value=self.config["location"])
        location_entry = ttk.Entry(location_frame, textvariable=self.location_var, width=20)
        location_entry.grid(row=0, column=1, pady=5, padx=5, sticky=tk.W+tk.E)
        
        # Working Hours
        hours_frame = ttk.Frame(user_settings)
        hours_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(hours_frame, text="Working Hours:").grid(row=0, column=0, sticky=tk.W, pady=5)
        
        hours_entry_frame = ttk.Frame(hours_frame)
        hours_entry_frame.grid(row=0, column=1, pady=5, padx=5)
        
        self.start_hour_var = tk.StringVar(value=self.config["working_hours"]["start"])
        start_entry = ttk.Entry(hours_entry_frame, textvariable=self.start_hour_var, width=7)
        start_entry.pack(side=tk.LEFT, padx=(0, 5))
        
        ttk.Label(hours_entry_frame, text="-").pack(side=tk.LEFT)
        
        self.end_hour_var = tk.StringVar(value=self.config["working_hours"]["end"])
        end_entry = ttk.Entry(hours_entry_frame, textvariable=self.end_hour_var, width=7)
        end_entry.pack(side=tk.LEFT, padx=(5, 0))
        
        # API Key
        api_frame = ttk.Frame(user_settings)
        api_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(api_frame, text="OpenWeatherMap API Key:").grid(row=0, column=0, sticky=tk.W, pady=5)
        
        self.api_var = tk.StringVar(value=self.config["api_key"])
        api_entry = ttk.Entry(api_frame, textvariable=self.api_var, width=25)
        api_entry.grid(row=0, column=1, pady=5, padx=5, sticky=tk.W+tk.E)
        
        # Get API Key Button
        get_api_btn = ttk.Button(api_frame, text="Get API Key", command=self.open_api_website)
        get_api_btn.grid(row=1, column=1, pady=5, padx=5, sticky=tk.E)
        
        # Time Intervals Settings
        intervals_frame = ttk.Frame(user_settings)
        intervals_frame.pack(fill=tk.X, pady=10)
        
        ttk.Label(intervals_frame, text="Notification Intervals:").pack(anchor=tk.W, pady=(0, 5))
        
        # Radio buttons for interval options
        self.interval_type_var = tk.StringVar(
            value="custom" if self.config["custom_intervals"] else "auto"
        )
        
        auto_radio = ttk.Radiobutton(intervals_frame, text="Auto-generate based on working hours", 
                                    variable=self.interval_type_var, value="auto", 
                                    command=self.toggle_intervals_input)
        auto_radio.pack(anchor=tk.W, pady=2)
        
        custom_radio = ttk.Radiobutton(intervals_frame, text="Custom intervals", 
                                      variable=self.interval_type_var, value="custom", 
                                      command=self.toggle_intervals_input)
        custom_radio.pack(anchor=tk.W, pady=2)
        
        # Custom intervals entry
        self.custom_intervals_frame = ttk.Frame(intervals_frame)
        self.custom_intervals_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(self.custom_intervals_frame, 
                text="Enter comma-separated times (HH:MM):").pack(anchor=tk.W, pady=(5, 0))
        
        custom_intervals_str = ", ".join(self.config["custom_intervals"]) if self.config["custom_intervals"] else ""
        self.custom_intervals_var = tk.StringVar(value=custom_intervals_str)
        self.custom_intervals_entry = ttk.Entry(self.custom_intervals_frame, textvariable=self.custom_intervals_var)
        self.custom_intervals_entry.pack(fill=tk.X, pady=5)
        
        # Right column - App settings
        right_col = ttk.Frame(settings_container, padding=10)
        right_col.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        
        # Notification settings card
        notification_settings = ttk.LabelFrame(right_col, text="Notification Settings", padding=10)
        notification_settings.pack(fill=tk.X, padx=5, pady=5)
        
        # Enable notifications
        self.notif_enabled_var = tk.BooleanVar(value=self.config.get("notification_enabled", True))
        notif_check = ttk.Checkbutton(notification_settings, text="Enable notifications", 
                                    variable=self.notif_enabled_var)
        notif_check.pack(anchor=tk.W, pady=5)
        
        # Notification sound
        self.notif_sound_var = tk.BooleanVar(value=self.config.get("notification_sound", True))
        sound_check = ttk.Checkbutton(notification_settings, text="Play sound with notifications", 
                                    variable=self.notif_sound_var)
        sound_check.pack(anchor=tk.W, pady=5)
        
        # Notification style
        style_frame = ttk.Frame(notification_settings)
        style_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(style_frame, text="Notification Style:").grid(row=0, column=0, sticky=tk.W, pady=5)
        
        self.notif_style_var = tk.StringVar(value=self.config.get("notification_style", "standard"))
        style_combo = ttk.Combobox(style_frame, textvariable=self.notif_style_var, width=15)
        style_combo["values"] = ("standard", "minimal", "detailed")
        style_combo["state"] = "readonly"
        style_combo.grid(row=0, column=1, pady=5, padx=5)
        
        # Test notification button
        test_notif_btn = ttk.Button(notification_settings, text="Test Notification", 
                                  command=self.show_test_notification)
        test_notif_btn.pack(fill=tk.X, pady=5)
        
        # Appearance settings card
        appearance_settings = ttk.LabelFrame(right_col, text="Appearance", padding=10)
        appearance_settings.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Theme selection
        theme_frame = ttk.Frame(appearance_settings)
        theme_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(theme_frame, text="Theme:").grid(row=0, column=0, sticky=tk.W, pady=5)
        
        self.theme_var = tk.StringVar(value=self.config.get("theme", "arc"))
        theme_combo = ttk.Combobox(theme_frame, textvariable=self.theme_var, width=15)
        theme_combo["values"] = AVAILABLE_THEMES
        theme_combo["state"] = "readonly"
        theme_combo.grid(row=0, column=1, pady=5, padx=5)
        
        # Color scheme selection
        color_frame = ttk.Frame(appearance_settings)
        color_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(color_frame, text="Color Scheme:").grid(row=0, column=0, sticky=tk.W, pady=5)
        
        self.color_scheme_var = tk.StringVar(value=self.config.get("color_scheme", "blue"))
        color_combo = ttk.Combobox(color_frame, textvariable=self.color_scheme_var, width=15)
        color_combo["values"] = list(COLOR_SCHEMES.keys())
        color_combo["state"] = "readonly"
        color_combo.grid(row=0, column=1, pady=5, padx=5)
        
        # Reset settings button
        reset_btn = ttk.Button(right_col, text="Reset to Defaults", command=self.reset_settings)
        reset_btn.pack(pady=10)
        
        # Initialize the custom intervals visibility based on current setting
        self.toggle_intervals_input()
    
    def toggle_intervals_input(self):
        """Toggle visibility of custom intervals input based on selection"""
        if self.interval_type_var.get() == "auto":
            for child in self.custom_intervals_frame.winfo_children():
                child.configure(state=tk.DISABLED)
        else:
            for child in self.custom_intervals_frame.winfo_children():
                child.configure(state=tk.NORMAL)
    
    def setup_history_tab(self):
        """Set up the history tab"""
        # Header
        header_frame = ttk.Frame(self.history_tab)
        header_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(header_frame, text="Hydration History", style="Header.TLabel").pack(side=tk.LEFT)
        
        # Main content
        content_frame = ttk.Frame(self.history_tab)
        content_frame.pack(fill=tk.BOTH, expand=True)
        
        # Initialize history if not present
        if "history" not in self.config:
            self.config["history"] = {}
            save_user_data(self.config)
        
        # Create chart
        self.setup_history_chart(content_frame)
        
        # History table
        table_frame = ttk.Frame(content_frame)
        table_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        
        ttk.Label(table_frame, text="Daily Records", style="Subheader.TLabel").pack(anchor=tk.W, pady=(0, 10))
        
        # Create table with scrollbar
        table_container = ttk.Frame(table_frame)
        table_container.pack(fill=tk.BOTH, expand=True)
        
        # Columns
        columns = ("date", "amount", "goal", "percentage")
        self.history_tree = ttk.Treeview(table_container, columns=columns, show="headings")
        
        # Define headings
        self.history_tree.heading("date", text="Date")
        self.history_tree.heading("amount", text="Amount (L)")
        self.history_tree.heading("goal", text="Goal (L)")
        self.history_tree.heading("percentage", text="Completion")
        
        # Define column widths
        self.history_tree.column("date", width=120)
        self.history_tree.column("amount", width=100)
        self.history_tree.column("goal", width=100)
        self.history_tree.column("percentage", width=100)
        
        # Add a scrollbar
        scrollbar = ttk.Scrollbar(table_container, orient=tk.VERTICAL, command=self.history_tree.yview)
        self.history_tree.configure(yscrollcommand=scrollbar.set)
        
        # Pack the treeview and scrollbar
        self.history_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Populate the table with history data
        self.populate_history_table()
    
    def setup_history_chart(self, parent):
        """Create a chart showing hydration history"""
        chart_frame = ttk.Frame(parent)
        chart_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        
        # Create the figure
        fig = plt.Figure(figsize=(5, 3), dpi=100)
        ax = fig.add_subplot(111)
        
        # Create canvas widget
        self.chart_canvas = FigureCanvasTkAgg(fig, master=chart_frame)
        self.chart_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        
        # Get history data
        dates = []
        amounts = []
        goal_line = []
        
        # Sort dates
        sorted_dates = sorted(self.config["history"].keys())
        
        for date_str in sorted_dates[-7:]:  # Last 7 days
            dates.append(date_str)
            amounts.append(self.config["history"][date_str])
            goal_line.append(self.config["daily_goal"])
        
        # Create the plot
        if dates:  # Only plot if we have data
            x = range(len(dates))
            
            # Bar chart for amounts
            bars = ax.bar(x, amounts, color=self.colors["secondary"], label="Water Intake")
            
            # Line for goal
            ax.plot(x, goal_line, 'r--', label="Goal")
            
            # Add data labels on bars
            for i, v in enumerate(amounts):
                ax.text(i, v + 0.1, f"{v:.1f}L", ha='center')
            
            # Format the plot
            ax.set_ylabel('Liters')
            ax.set_title('Weekly Hydration History')
            ax.set_xticks(x)
            ax.set_xticklabels([d[-5:] for d in dates], rotation=45)  # Only show MM-DD part
            ax.legend()
            
            fig.tight_layout()
        else:
            # No data message
            ax.text(0.5, 0.5, "No history data available", 
                   horizontalalignment='center', verticalalignment='center',
                   transform=ax.transAxes)
            ax.set_xticks([])
            ax.set_yticks([])
        
        # Update the canvas
        self.chart_canvas.draw()
    
    def populate_history_table(self):
        """Populate the history table with data"""
        # Clear existing items
        for item in self.history_tree.get_children():
            self.history_tree.delete(item)
        
        # Sort dates in reverse order (newest first)
        sorted_dates = sorted(self.config["history"].keys(), reverse=True)
        
        # Add history items
        for date_str in sorted_dates:
            amount = self.config["history"][date_str]
            goal = self.config["daily_goal"]
            percentage = (amount / goal) * 100
            
            # Format date
            try:
                date_obj = datetime.datetime.strptime(date_str, "%Y-%m-%d")
                formatted_date = date_obj.strftime("%b %d, %Y")
            except:
                formatted_date = date_str
            
            self.history_tree.insert("", tk.END, values=(
                formatted_date,
                f"{amount:.2f}",
                f"{goal:.2f}",
                f"{percentage:.1f}%"
            ))
    
    def setup_about_tab(self):
        """Set up the about tab"""
        # Create scrollable frame
        canvas = tk.Canvas(self.about_tab)
        scrollbar = ttk.Scrollbar(self.about_tab, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Header
        ttk.Label(scrollable_frame, text="Hydration Coach", style="Header.TLabel").pack(anchor=tk.W, pady=(0, 5))
        ttk.Label(scrollable_frame, text="Version 1.0", font=("Arial", 10, "italic")).pack(anchor=tk.W, pady=(0, 10))
        
        # About info
        about_text = (
            "Hydration Coach is a personal assistant that helps you maintain proper "
            "hydration throughout the day based on your activity level and local weather conditions."
        )
        
        ttk.Label(scrollable_frame, text=about_text, wraplength=600).pack(anchor=tk.W, pady=10)
        
        # Features
        ttk.Label(scrollable_frame, text="Features", style="Subheader.TLabel").pack(anchor=tk.W, pady=(10, 5))
        
        features = [
            "Personalized daily water intake goals",
            "Smart notifications based on your working hours",
            "Weather-adjusted hydration recommendations",
            "Activity level consideration for accurate targets",
            "Progress tracking and history visualization",
            "Customizable notification settings",
            "Modern and user-friendly interface"
        ]
        
        for feature in features:
            ttk.Label(scrollable_frame, text=f"• {feature}").pack(anchor=tk.W, padx=10)
        
        # Weather data info
        ttk.Label(scrollable_frame, text="Weather Data", style="Subheader.TLabel").pack(anchor=tk.W, pady=(15, 5))
        
        weather_text = (
            "Hydration Coach uses OpenWeatherMap to retrieve local weather data and adjust "
            "your hydration recommendations based on temperature and humidity levels. "
            "You will need to obtain a free API key from OpenWeatherMap to enable this feature."
        )
        
        ttk.Label(scrollable_frame, text=weather_text, wraplength=600).pack(anchor=tk.W, pady=5)
        
        api_btn = ttk.Button(scrollable_frame, text="Get API Key", command=self.open_api_website)
        api_btn.pack(anchor=tk.W, pady=5)
        
        # Credits
        ttk.Label(scrollable_frame, text="Credits", style="Subheader.TLabel").pack(anchor=tk.W, pady=(15, 5))
        
        credits_text = "Developed by Replit User"
        ttk.Label(scrollable_frame, text=credits_text).pack(anchor=tk.W, pady=5)
        
        # License
        ttk.Label(scrollable_frame, text="License", style="Subheader.TLabel").pack(anchor=tk.W, pady=(15, 5))
        
        license_text = "This software is open source and free to use, modify, and distribute."
        ttk.Label(scrollable_frame, text=license_text).pack(anchor=tk.W, pady=5)
    
    def open_api_website(self):
        """Open the OpenWeatherMap website to get an API key"""
        webbrowser.open("https://openweathermap.org/api")
    
    def show_log_dialog(self):
        """Show a dialog to log water intake"""
        try:
            amount = simpledialog.askfloat("Log Water", "Enter amount in liters:", 
                                         minvalue=0.01, maxvalue=5.0)
            if amount is not None:
                self.log_water_intake(amount)
        except:
            messagebox.showerror("Input Error", "Please enter a valid number.")
    
    def log_water_intake(self, amount):
        """Log water intake and update the UI"""
        if amount <= 0:
            return
        
        # Update config
        self.config["progress"] += amount
        self.config["last_update"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        save_user_data(self.config)
        
        # Update UI elements
        self.refresh_dashboard()
        
        # Show confirmation
        messagebox.showinfo("Water Logged", f"Added {amount:.2f} liters to your daily progress!")
    
    def refresh_dashboard(self):
        """Refresh the dashboard UI with current data"""
        # Update progress bar
        progress_value = self.config["progress"] / self.config["daily_goal"]
        progress_value = min(1.0, max(0.0, progress_value))  # Ensure between 0 and 1
        self.progress_bar.set_progress(progress_value)
        
        # Update labels
        self.current_label.config(text=f"{self.config['progress']:.2f} L")
        self.goal_label.config(text=f"{self.config['daily_goal']:.2f} L")
        
        remaining = max(0, self.config["daily_goal"] - self.config["progress"])
        self.remaining_label.config(text=f"{remaining:.2f} L")
        
        # Update status
        if self.config["last_update"]:
            try:
                last_update_dt = datetime.datetime.strptime(
                    self.config["last_update"], "%Y-%m-%d %H:%M:%S"
                )
                last_update_str = last_update_dt.strftime("%b %d, %Y %I:%M %p")
                self.status_label.config(text=f"Last updated: {last_update_str}")
            except:
                self.status_label.config(text=f"Last updated: {self.config['last_update']}")
        
        # Update notification status
        notif_status = "Enabled" if self.config["notification_enabled"] else "Disabled"
        self.notif_status_label.config(text=f"Notifications: {notif_status}")
        
        # Update working hours
        self.work_hours_label.config(
            text=f"{self.config['working_hours']['start']} - {self.config['working_hours']['end']}"
        )
        
        # Update location
        self.location_label.config(text=f"Location: {self.config['location']}")
        
        # Update notification times
        self.times_listbox.delete(0, tk.END)
        
        if self.config["custom_intervals"] and len(self.config["custom_intervals"]) > 0:
            notification_times = self.config["custom_intervals"]
        else:
            notification_times = generate_intervals(self.config)
            
        for time_str in notification_times:
            self.times_listbox.insert(tk.END, time_str)
        
        # Update weather info
        self.update_weather_info()
    
    def update_weather_info(self):
        """Update the weather information display"""
        # Only update if we have an API key
        if not self.config["api_key"]:
            self.weather_status_label.config(text="Weather data unavailable - No API key")
            return
        
        # Try to get weather data
        try:
            weather_data = get_weather_data(self.config["location"], self.config["api_key"])
            
            # Update labels with weather data
            temp_kelvin = weather_data.get("main", {}).get("temp", 0)
            temp_celsius = temp_kelvin - 273.15
            self.temp_label.config(text=f"Temperature: {temp_celsius:.1f}°C")
            
            humidity = weather_data.get("main", {}).get("humidity", 0)
            self.humidity_label.config(text=f"Humidity: {humidity}%")
            
            condition = weather_data.get("weather", [{}])[0].get("main", "Unknown")
            self.weather_status_label.config(text=f"Current weather: {condition}")
            
            weather_factor = calculate_weather_factor(weather_data)
            self.factor_label.config(text=f"Hydration Factor: {weather_factor:.2f}x")
            
        except Exception as e:
            self.weather_status_label.config(text=f"Weather data error: {str(e)}")
    
    def save_settings(self):
        """Save settings from the UI to the config"""
        try:
            # Validate time formats
            start_time = self.start_hour_var.get()
            end_time = self.end_hour_var.get()
            
            # Validate start and end times
            try:
                parse_time(start_time)
                parse_time(end_time)
            except ValueError as e:
                messagebox.showerror("Time Format Error", str(e))
                return
            
            # Make sure start time is before end time
            if time_to_minutes(start_time) >= time_to_minutes(end_time):
                messagebox.showerror("Time Error", "Start time must be before end time")
                return
            
            # Validate goal
            try:
                goal = float(self.goal_var.get())
                if goal <= 0:
                    raise ValueError("Goal must be positive")
            except:
                messagebox.showerror("Input Error", "Please enter a valid goal amount")
                return
            
            # Process custom intervals if selected
            custom_intervals = []
            if self.interval_type_var.get() == "custom":
                intervals_str = self.custom_intervals_var.get()
                if intervals_str:
                    # Split by commas and validate each time
                    try:
                        time_strings = intervals_str.split(",")
                        for time_str in time_strings:
                            time_str = time_str.strip()
                            parse_time(time_str)  # Validate format
                            custom_intervals.append(time_str)
                    except ValueError as e:
                        messagebox.showerror("Time Format Error", 
                                           f"Invalid time in intervals: {str(e)}")
                        return
            
            # Update the config with new values
            self.config["daily_goal"] = goal
            self.config["activity_level"] = self.activity_var.get()
            self.config["location"] = self.location_var.get()
            self.config["working_hours"]["start"] = start_time
            self.config["working_hours"]["end"] = end_time
            self.config["api_key"] = self.api_var.get()
            
            # Update intervals based on selection
            if self.interval_type_var.get() == "auto":
                self.config["custom_intervals"] = []
            else:
                self.config["custom_intervals"] = custom_intervals
            
            # Update notification settings
            self.config["notification_enabled"] = self.notif_enabled_var.get()
            self.config["notification_sound"] = self.notif_sound_var.get()
            self.config["notification_style"] = self.notif_style_var.get()
            
            # Update appearance settings
            old_theme = self.config.get("theme")
            old_color_scheme = self.config.get("color_scheme")
            
            self.config["theme"] = self.theme_var.get()
            self.config["color_scheme"] = self.color_scheme_var.get()
            
            # Save the configuration
            save_user_data(self.config)
            
            # Update the UI
            self.refresh_dashboard()
            
            # Restart the scheduler if notification settings changed
            self.restart_scheduler()
            
            # Show theme change warning if needed
            if old_theme != self.theme_var.get() or old_color_scheme != self.color_scheme_var.get():
                messagebox.showinfo("Theme Changed", 
                                  "Theme changes will take full effect after restarting the application.")
            
            messagebox.showinfo("Settings Saved", "Your settings have been saved successfully.")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save settings: {str(e)}")
    
    def reset_settings(self):
        """Reset settings to defaults"""
        confirm = messagebox.askyesno("Confirm Reset", 
                                     "Are you sure you want to reset all settings to defaults?\n\nYour progress and history will be preserved.")
        if confirm:
            # Preserve progress and history
            progress = self.config.get("progress", 0.0)
            last_update = self.config.get("last_update")
            history = self.config.get("history", {})
            
            # Reset to defaults
            self.config = DEFAULT_CONFIG.copy()
            
            # Restore preserved data
            self.config["progress"] = progress
            self.config["last_update"] = last_update
            self.config["history"] = history
            
            save_user_data(self.config)
            
            # Update UI with new values
            self.update_settings_ui()
            self.refresh_dashboard()
            
            messagebox.showinfo("Settings Reset", "Settings have been reset to defaults")
    
    def update_settings_ui(self):
        """Update settings UI with current config values"""
        # User settings
        self.goal_var.set(self.config["daily_goal"])
        self.activity_var.set(self.config["activity_level"])
        self.location_var.set(self.config["location"])
        self.start_hour_var.set(self.config["working_hours"]["start"])
        self.end_hour_var.set(self.config["working_hours"]["end"])
        self.api_var.set(self.config["api_key"])
        
        # Intervals
        self.interval_type_var.set("custom" if self.config["custom_intervals"] else "auto")
        custom_intervals_str = ", ".join(self.config["custom_intervals"])
        self.custom_intervals_var.set(custom_intervals_str)
        self.toggle_intervals_input()
        
        # Notification settings
        self.notif_enabled_var.set(self.config.get("notification_enabled", True))
        self.notif_sound_var.set(self.config.get("notification_sound", True))
        self.notif_style_var.set(self.config.get("notification_style", "standard"))
        
        # Appearance settings
        self.theme_var.set(self.config.get("theme", "arc"))
        self.color_scheme_var.set(self.config.get("color_scheme", "blue"))
    
    def start_scheduler(self):
        """Start the notification scheduler in a separate thread"""
        if self.scheduler_thread and self.scheduler_thread.is_alive():
            return
        
        self.scheduler_running = True
        self.scheduler_thread = threading.Thread(target=self.run_scheduler)
        self.scheduler_thread.daemon = True
        self.scheduler_thread.start()
    
    def stop_scheduler(self):
        """Stop the notification scheduler thread"""
        self.scheduler_running = False
        if self.scheduler_thread:
            self.scheduler_thread.join(timeout=1.0)
    
    def restart_scheduler(self):
        """Restart the notification scheduler"""
        self.stop_scheduler()
        schedule.clear()
        
        if self.config["notification_enabled"]:
            self.start_scheduler()
    
    def run_scheduler(self):
        """Run the notification scheduler loop"""
        # Set up notification schedule
        schedule.clear()
        
        # Determine notification times
        if self.config["custom_intervals"] and len(self.config["custom_intervals"]) > 0:
            notification_times = self.config["custom_intervals"]
        else:
            notification_times = generate_intervals(self.config)
        
        # Schedule notifications
        for time_str in notification_times:
            schedule.every().day.at(time_str).do(self.notify_drink_water)
        
        # Schedule a midnight job to reset progress
        schedule.every().day.at("00:00").do(self.reset_daily_progress)
        
        # Run the scheduler loop
        while self.scheduler_running:
            schedule.run_pending()
            time.sleep(1)
    
    def reset_daily_progress(self):
        """Reset daily progress and update history"""
        if check_reset_progress(self.config):
            # Update UI if app is running
            self.root.after(0, self.refresh_dashboard)
            self.root.after(0, self.populate_history_table)
            
            # Update the history chart
            self.root.after(0, lambda: self.setup_history_chart(self.history_tab))
    
    def notify_drink_water(self):
        """Show a notification to drink water"""
        if not self.config["notification_enabled"]:
            return
        
        # Calculate recommended amount
        recommended_amount = calculate_recommended_amount(self.config)
        
        progress_percent = (self.config["progress"] / self.config["daily_goal"]) * 100
        remaining = self.config["daily_goal"] - self.config["progress"]
        
        # Create message based on notification style
        if self.config.get("notification_style") == "minimal":
            message = f"Time to drink water! ({recommended_amount:.2f}L recommended)"
        elif self.config.get("notification_style") == "detailed":
            message = (f"Time to drink water! Recommended: {recommended_amount:.2f}L\n"
                      f"Progress: {self.config['progress']:.2f}/{self.config['daily_goal']:.2f}L "
                      f"({progress_percent:.1f}%)\n"
                      f"Remaining: {remaining:.2f}L\n"
                      f"Activity: {self.config['activity_level'].capitalize()}")
        else:  # standard
            message = (f"Time to drink water! Recommended: {recommended_amount:.2f}L\n"
                      f"Progress: {self.config['progress']:.2f}/{self.config['daily_goal']:.2f}L "
                      f"({progress_percent:.1f}%)\n"
                      f"Remaining: {remaining:.2f}L")
        
        # Check if GUI is running
        if self.root.winfo_exists():
            # Create a custom notification window if app is in foreground
            self.root.after(0, lambda: NotificationWindow(
                self.root,
                "Hydration Coach",
                message,
                style=self.config.get("notification_style", "standard"),
                sound=self.config.get("notification_sound", True),
                on_drink_callback=lambda: self.log_water_intake(recommended_amount)
            ))
        else:
            # Fall back to system notification if app is in background
            send_notification("Hydration Coach", message)
        
        return recommended_amount
    
    def show_test_notification(self):
        """Show a test notification with current settings"""
        style = self.notif_style_var.get()
        sound = self.notif_sound_var.get()
        
        # Sample message based on selected style
        if style == "minimal":
            message = "This is a test notification. (0.25L recommended)"
        elif style == "detailed":
            message = ("This is a test notification. Recommended: 0.25L\n"
                      "Progress: 1.25/2.00L (62.5%)\n"
                      "Remaining: 0.75L\n"
                      "Activity: Moderate")
        else:  # standard
            message = ("This is a test notification. Recommended: 0.25L\n"
                      "Progress: 1.25/2.00L (62.5%)\n"
                      "Remaining: 0.75L")
        
        # Show the notification
        NotificationWindow(
            self.root,
            "Test Notification",
            message,
            style=style,
            sound=sound
        )
    
    def reset_progress(self):
        """Reset current progress with confirmation"""
        if self.config["progress"] <= 0:
            messagebox.showinfo("No Progress", "There is no progress to reset.")
            return
            
        # Ask for confirmation
        result = messagebox.askyesno(
            "Reset Progress", 
            f"Are you sure you want to reset your current progress ({self.config['progress']:.2f} L)?\n\n"
            "This will set your current water intake to 0.",
            icon="warning"
        )
        
        if not result:
            return
            
        # Store current value for animation
        old_progress = self.config["progress"]
        
        # Reset progress
        self.config["progress"] = 0.0
        self.config["last_update"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Save changes
        save_user_data(self.config)
        
        # Update UI
        progress_value = self.config["progress"] / self.config["daily_goal"]
        self.progress_bar.set_progress(progress_value)
        self.refresh_dashboard()
        
        # Show confirmation
        messagebox.showinfo("Progress Reset", f"Your progress of {old_progress:.2f} L has been reset to 0.")
    
    def on_close(self):
        """Handle window close event"""
        # Stop the scheduler
        self.stop_scheduler()
        
        # Save the configuration
        save_user_data(self.config)
        
        # Destroy the window
        self.root.destroy()

def main():
    """Main function"""
    # Use ThemedTk for better looking interface
    try:
        root = ThemedTk(theme="arc")
    except:
        # Fall back to regular Tk if ThemedTk fails
        root = tk.Tk()
    
    # Set window icon
    try:
        # Set taskbar icon (Windows)
        root.iconbitmap("icon.ico")
    except:
        # Fallback for Linux
        pass
    
    # Create the application
    app = HydrationCoachApp(root)
    
    # Start the main loop
    root.mainloop()

if __name__ == "__main__":
    main()