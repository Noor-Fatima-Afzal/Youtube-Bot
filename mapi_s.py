import streamlit as st
import asyncio
import os
from playwright.async_api import async_playwright
import json
from datetime import datetime
import sys
import time

# CRITICAL FIX for Windows + Streamlit + Playwright
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# Page configuration
st.set_page_config(
    page_title="YouTube Multi-Account Automation",
    page_icon="🎥",
    layout="wide"
)

# Constants
CHANNEL_URL = "https://www.youtube.com/@kitabiduniya-k3y"
SESSION_DIR = "./browser_sessions"

# Initialize session state
if 'phase' not in st.session_state:
    st.session_state.phase = 'account_selection'
if 'num_accounts' not in st.session_state:
    st.session_state.num_accounts = 0
if 'current_login_account' not in st.session_state:
    st.session_state.current_login_account = 0
if 'logged_in_accounts' not in st.session_state:
    st.session_state.logged_in_accounts = []
if 'automation_results' not in st.session_state:
    st.session_state.automation_results = []
if 'logs' not in st.session_state:
    st.session_state.logs = []
if 'live_log_placeholder' not in st.session_state:
    st.session_state.live_log_placeholder = None

def add_log(message, type="info"):
    """Add a log message with timestamp and update UI"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    log_entry = {
        'time': timestamp,
        'message': message,
        'type': type
    }
    st.session_state.logs.append(log_entry)
    
    # Print to console as well
    icon = "✅" if type == "success" else "❌" if type == "error" else "⚠️" if type == "warning" else "ℹ️"
    print(f"{icon} [{timestamp}] {message}")
    
    # Update live placeholder if it exists
    if st.session_state.live_log_placeholder is not None:
        with st.session_state.live_log_placeholder.container():
            # Show last 15 logs
            for log in reversed(st.session_state.logs[-15:]):
                if log['type'] == 'success':
                    st.success(f"[{log['time']}] {log['message']}", icon="✅")
                elif log['type'] == 'error':
                    st.error(f"[{log['time']}] {log['message']}", icon="❌")
                elif log['type'] == 'warning':
                    st.warning(f"[{log['time']}] {log['message']}", icon="⚠️")
                else:
                    st.info(f"[{log['time']}] {log['message']}", icon="ℹ️")

async def verify_login(page):
    """Verify if user is actually logged into YouTube"""
    try:
        add_log("Checking login status...")
        
        # Try to navigate if not on YouTube
        if "youtube.com" not in page.url:
            add_log("Navigating to YouTube...")
            try:
                await page.goto("https://www.youtube.com", timeout=60000, wait_until="domcontentloaded")
                await page.wait_for_timeout(4000)
            except Exception as e:
                add_log(f"Navigation error: {str(e)[:100]}", "warning")
                await page.wait_for_timeout(2000)
        else:
            await page.wait_for_timeout(2000)
        
        # Reload to ensure fresh state
        try:
            await page.reload(wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)
        except:
            add_log("Reload timeout, continuing anyway...", "warning")
            await page.wait_for_timeout(2000)
        
        # Check for Sign In button (means NOT logged in)
        sign_in_buttons = page.locator('a:has-text("Sign in"), tp-yt-paper-button:has-text("Sign in")')
        
        try:
            sign_in_count = await sign_in_buttons.count()
            if sign_in_count > 0:
                for i in range(sign_in_count):
                    try:
                        btn = sign_in_buttons.nth(i)
                        is_visible = await btn.is_visible(timeout=2000)
                        if is_visible:
                            display = await btn.evaluate('el => window.getComputedStyle(el).display')
                            opacity = await btn.evaluate('el => window.getComputedStyle(el).opacity')
                            visibility = await btn.evaluate('el => window.getComputedStyle(el).visibility')
                            
                            if display != 'none' and opacity != '0' and visibility != 'hidden':
                                add_log("LOGIN FAILED - Sign In button is visible", "error")
                                return False
                    except:
                        continue
        except:
            pass
        
        # Look for user avatar/profile (means logged in)
        avatar_selectors = [
            'button#avatar-btn img',
            'img#avatar',
            'ytd-topbar-menu-button-renderer img',
            'button[aria-label*="Google Account"] img',
            'yt-img-shadow#avatar img',
            '#avatar > img'
        ]
        
        for selector in avatar_selectors:
            try:
                avatar = page.locator(selector).first
                count = await avatar.count()
                if count > 0:
                    try:
                        is_visible = await avatar.is_visible(timeout=2000)
                        if is_visible:
                            src = await avatar.get_attribute('src')
                            if src and ('googleusercontent.com' in src or 'yt3.ggpht.com' in src or 'ggpht.com' in src):
                                add_log("✓ LOGIN VERIFIED - Found user avatar!", "success")
                                return True
                    except:
                        continue
            except:
                continue
        
        # Check for user menu button
        try:
            user_menu = page.locator('button#avatar-btn').first
            if await user_menu.count() > 0:
                is_visible = await user_menu.is_visible(timeout=2000)
                if is_visible:
                    aria_label = await user_menu.get_attribute('aria-label')
                    if aria_label and 'account' in aria_label.lower():
                        add_log("✓ LOGIN VERIFIED - Found Account menu", "success")
                        return True
        except:
            pass
        
        add_log("Could not verify login status", "warning")
        return False
        
    except Exception as e:
        add_log(f"Error verifying login: {str(e)[:100]}", "error")
        return False

async def login_youtube_manual(page, account_num, total_accounts):
    """Manual login - user does everything"""
    try:
        add_log(f"Opening Google Sign In page for account {account_num}/{total_accounts}...", "info")
        
        try:
            await page.goto(
                "https://accounts.google.com/signin/v2/identifier?service=youtube&continue=https://www.youtube.com",
                timeout=60000,
                wait_until="domcontentloaded"
            )
            await page.wait_for_timeout(2000)
        except Exception as e:
            add_log(f"Navigation timeout: {str(e)[:100]}", "warning")
            add_log("Trying alternate login method...", "info")
            try:
                await page.goto("https://www.youtube.com", timeout=60000, wait_until="domcontentloaded")
                await page.wait_for_timeout(3000)
                # Try to click sign in button
                sign_in = page.locator('a:has-text("Sign in")').first
                if await sign_in.count() > 0:
                    await sign_in.click()
                    await page.wait_for_timeout(2000)
            except:
                add_log("Could not navigate to login page", "error")
                return False
        
        add_log("⏳ Waiting for you to complete login manually...", "info")
        add_log("You have up to 5 minutes to login", "info")
        
        # Wait up to 5 minutes for manual login
        for attempt in range(60):  # 60 attempts x 5 seconds = 5 minutes
            await page.wait_for_timeout(5000)
            
            try:
                current_url = page.url
            except:
                continue
            
            if "youtube.com" in current_url:
                avatar_found = False
                avatar_selectors = [
                    'button#avatar-btn img',
                    'ytd-topbar-menu-button-renderer img',
                ]
                
                for selector in avatar_selectors:
                    try:
                        avatar = page.locator(selector).first
                        if await avatar.count() > 0:
                            is_visible = await avatar.is_visible(timeout=1000)
                            if is_visible:
                                src = await avatar.get_attribute('src')
                                if src and ('googleusercontent.com' in src or 'yt3.ggpht.com' in src or 'ggpht.com' in src):
                                    avatar_found = True
                                    break
                    except:
                        continue
                
                if avatar_found:
                    add_log("✓ Detected user avatar! Login successful!", "success")
                    await page.wait_for_timeout(3000)
                    return await verify_login(page)
                else:
                    try:
                        signin_btn = page.locator('a:has-text("Sign in")').first
                        if await signin_btn.count() > 0 and await signin_btn.is_visible(timeout=1000):
                            if attempt % 6 == 0:
                                add_log(f"Still waiting... ({(attempt + 1) * 5} seconds elapsed)", "info")
                            continue
                    except:
                        pass
            else:
                if attempt % 6 == 0:
                    add_log(f"Still on login page... ({(attempt + 1) * 5} seconds elapsed)", "info")
        
        add_log("⚠ Login timeout (5 minutes). Verifying status...", "warning")
        return await verify_login(page)
        
    except Exception as e:
        add_log(f"Error during manual login: {str(e)[:100]}", "error")
        return await verify_login(page)

async def subscribe_channel(page):
    """Subscribe to a YouTube channel"""
    try:
        add_log(f"Navigating to channel: {CHANNEL_URL}", "info")
        await page.goto(CHANNEL_URL, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(3000)
        
        selectors = [
            'ytd-subscribe-button-renderer button[aria-label*="Subscribe"]',
            'yt-button-shape button:has-text("Subscribe")',
            '#subscribe-button button',
            'ytd-button-renderer.ytd-subscribe-button-renderer button'
        ]
        
        subscribed = False
        for selector in selectors:
            try:
                button = page.locator(selector).first
                if await button.count() > 0:
                    await button.wait_for(state="visible", timeout=5000)
                    button_text = await button.inner_text()
                    
                    if "subscribed" in button_text.lower():
                        add_log("✓ Already subscribed to this channel", "success")
                        subscribed = True
                        break
                    else:
                        await button.click()
                        add_log("✓ Subscribed successfully!", "success")
                        await page.wait_for_timeout(2000)
                        subscribed = True
                        break
            except:
                continue
        
        if not subscribed:
            add_log("⚠ Could not find subscribe button. May already be subscribed.", "warning")
            
    except Exception as e:
        add_log(f"Error subscribing to channel: {str(e)[:100]}", "error")

async def get_video_duration(page):
    """Get the total duration of the video in seconds"""
    try:
        duration_selectors = [
            '.ytp-time-duration',
            'span.ytp-time-duration'
        ]
        
        for selector in duration_selectors:
            try:
                duration_element = page.locator(selector).first
                if await duration_element.count() > 0:
                    duration_text = await duration_element.inner_text()
                    parts = duration_text.strip().split(':')
                    if len(parts) == 2:  # MM:SS
                        minutes, seconds = map(int, parts)
                        total_seconds = minutes * 60 + seconds
                        return total_seconds
                    elif len(parts) == 3:  # HH:MM:SS
                        hours, minutes, seconds = map(int, parts)
                        total_seconds = hours * 3600 + minutes * 60 + seconds
                        return total_seconds
            except:
                continue
        
        return None
    except Exception as e:
        add_log(f"Error getting video duration: {str(e)[:100]}", "error")
        return None

async def watch_video_until_end(page, video_num):
    """Watch the video until it ends"""
    try:
        add_log(f"📺 Starting to watch video {video_num}...", "info")
        
        await page.wait_for_timeout(3000)
        
        # Mute the video
        try:
            video_element = page.locator('video').first
            if await video_element.count() > 0:
                await video_element.evaluate('video => video.muted = true')
                add_log("🔇 Video muted", "info")
        except:
            pass
        
        duration = await get_video_duration(page)
        
        if duration:
            add_log(f"⏱️  Video duration: {duration} seconds ({duration // 60}m {duration % 60}s)", "info")
            watch_time = duration + 5
            add_log(f"👀 Watching video for {watch_time} seconds...", "info")
        else:
            watch_time = 120
            add_log(f"⚠ Could not detect duration, watching for {watch_time} seconds...", "warning")
        
        # Play the video
        try:
            video_element = page.locator('video').first
            if await video_element.count() > 0:
                is_paused = await video_element.evaluate('video => video.paused')
                if is_paused:
                    add_log("▶️  Playing video...", "info")
                    await video_element.evaluate('video => video.play()')
                    await page.wait_for_timeout(2000)
                    is_still_paused = await video_element.evaluate('video => video.paused')
                    if not is_still_paused:
                        add_log("✓ Video is now playing", "success")
                    else:
                        add_log("⚠ Video still paused, but continuing...", "warning")
                else:
                    add_log("✓ Video is already playing", "success")
        except Exception as e:
            add_log(f"⚠ Could not start playback: {str(e)[:50]}", "warning")
        
        # Watch the video
        elapsed = 0
        check_interval = 10
        
        while elapsed < watch_time:
            await page.wait_for_timeout(check_interval * 1000)
            elapsed += check_interval
            
            if elapsed % 30 == 0:
                add_log(f"⏳ Watched {elapsed}/{watch_time} seconds...", "info")
            
            try:
                video_element = page.locator('video').first
                if await video_element.count() > 0:
                    current_time = await video_element.evaluate('video => video.currentTime')
                    duration_check = await video_element.evaluate('video => video.duration')
                    
                    if duration_check and current_time >= duration_check - 5:
                        add_log(f"✓ Video ended at {int(current_time)} seconds", "success")
                        break
            except:
                pass
        
        add_log(f"✓ Finished watching video {video_num}", "success")
        
    except Exception as e:
        add_log(f"⚠ Error while watching video: {str(e)[:100]}", "error")
        await page.wait_for_timeout(30000)

async def like_videos(page, num_videos=3):
    """Watch and like recent videos from the channel"""
    try:
        add_log("Navigating to channel videos...", "info")
        videos_url = CHANNEL_URL + "/videos"
        await page.goto(videos_url, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(4000)
        
        await page.evaluate("window.scrollBy(0, 500)")
        await page.wait_for_timeout(2000)
        
        video_links = await page.locator('a#video-title-link, a#video-title').all()
        
        if len(video_links) == 0:
            add_log("⚠ No videos found on this channel", "warning")
            return
        
        video_count = min(num_videos, len(video_links))
        add_log(f"Found {len(video_links)} videos. Processing {video_count} videos...", "info")
        
        urls = []
        for i in range(video_count):
            try:
                url = await video_links[i].get_attribute('href')
                if url:
                    urls.append(f"https://www.youtube.com{url}" if url.startswith('/') else url)
            except:
                continue
        
        for i, video_url in enumerate(urls):
            try:
                add_log(f"{'='*50}", "info")
                add_log(f"Processing video {i+1}/{video_count}...", "info")
                add_log(f"{'='*50}", "info")
                
                await page.goto(video_url, wait_until="domcontentloaded", timeout=60000)
                await page.wait_for_timeout(4000)
                
                await watch_video_until_end(page, i+1)
                
                add_log(f"👍 Attempting to like video {i+1}...", "info")
                
                like_selectors = [
                    'like-button-view-model button',
                    'ytd-toggle-button-renderer.ytd-menu-renderer button[aria-label*="like"]',
                    'segmented-like-dislike-button-view-model button:first-child',
                    '#segmented-like-button button'
                ]
                
                liked = False
                for selector in like_selectors:
                    try:
                        like_btn = page.locator(selector).first
                        if await like_btn.count() > 0:
                            await like_btn.wait_for(state="visible", timeout=5000)
                            
                            aria_pressed = await like_btn.get_attribute('aria-pressed')
                            aria_label = await like_btn.get_attribute('aria-label')
                            
                            if aria_pressed == 'true' or (aria_label and 'unlike' in aria_label.lower()):
                                add_log(f"✓ Video {i+1} already liked", "success")
                                liked = True
                                break
                            else:
                                await like_btn.click()
                                add_log(f"✓ Liked video {i+1}", "success")
                                await page.wait_for_timeout(1500)
                                liked = True
                                break
                    except:
                        continue
                
                if not liked:
                    add_log(f"⚠ Could not find like button for video {i+1}", "warning")
                
                add_log(f"✓ Completed video {i+1}/{video_count}", "success")
                    
            except Exception as e:
                add_log(f"⚠ Error processing video {i+1}: {str(e)[:100]}", "error")
                continue
                
    except Exception as e:
        add_log(f"Error in like_videos: {str(e)[:100]}", "error")

async def login_single_account(browser, account_num, total_accounts):
    """Login to a single account and save session"""
    add_log(f"{'='*60}", "info")
    add_log(f"LOGGING IN ACCOUNT {account_num}/{total_accounts}", "info")
    add_log(f"{'='*60}", "info")
    
    context = None
    page = None
    
    try:
        os.makedirs(SESSION_DIR, exist_ok=True)
        session_file = f"{SESSION_DIR}/account_{account_num}_session.json"
        
        context_options = {
            'viewport': None,
            'no_viewport': True,
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'java_script_enabled': True,
            'bypass_csp': True,
            'ignore_https_errors': True
        }
        
        if os.path.exists(session_file):
            add_log(f"✓ Found saved session for account {account_num}", "success")
            try:
                context_options['storage_state'] = session_file
            except Exception as e:
                add_log(f"⚠ Could not load session file: {str(e)[:50]}", "warning")
                add_log("Will create new session...", "info")
                try:
                    os.remove(session_file)
                except:
                    pass
        else:
            add_log(f"⚠ No saved session found for account {account_num}", "warning")
        
        context = await browser.new_context(**context_options)
        context.set_default_timeout(60000)
        
        page = await context.new_page()
        
        if os.path.exists(session_file):
            add_log("✓ Using saved session - checking if still valid...", "info")
            
            is_logged_in = await verify_login(page)
            
            if is_logged_in:
                add_log(f"✓✓✓ Session still valid! Already logged in", "success")
                await context.close()
                return True, session_file
            else:
                add_log("⚠ Saved session expired. Need to login again...", "warning")
                try:
                    os.remove(session_file)
                except:
                    pass
                
                manual_success = await login_youtube_manual(page, account_num, total_accounts)
                
                if not manual_success:
                    add_log(f"✗ LOGIN FAILED for account {account_num}", "error")
                    await context.close()
                    return False, None
                
                add_log(f"✓✓✓ Successfully logged in", "success")
                try:
                    await context.storage_state(path=session_file)
                    add_log(f"✓ Session saved for account {account_num}", "success")
                except Exception as e:
                    add_log(f"⚠ Could not save session: {str(e)[:50]}", "warning")
                
                await context.close()
                return True, session_file
        else:
            add_log("⚠ No saved session. Manual login required...", "warning")
            
            manual_success = await login_youtube_manual(page, account_num, total_accounts)
            
            if not manual_success:
                add_log(f"✗ LOGIN FAILED for account {account_num}", "error")
                await context.close()
                return False, None
            
            add_log(f"✓✓✓ Successfully logged in", "success")
            try:
                await context.storage_state(path=session_file)
                add_log(f"✓ Session saved for account {account_num}", "success")
            except Exception as e:
                add_log(f"⚠ Could not save session: {str(e)[:50]}", "warning")
            
            await context.close()
            return True, session_file
        
    except Exception as e:
        add_log(f"✗ Error logging in account: {str(e)[:100]}", "error")
        if context:
            try:
                await context.close()
            except:
                pass
        return False, None

async def automate_single_account(browser, account_num, total_accounts, session_file):
    """Process automation for a logged-in account"""
    add_log(f"{'='*60}", "info")
    add_log(f"AUTOMATING ACCOUNT {account_num}/{total_accounts}", "info")
    add_log(f"{'='*60}", "info")
    
    context = None
    page = None
    
    try:
        context_options = {
            'viewport': None,
            'no_viewport': True,
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'storage_state': session_file,
            'java_script_enabled': True,
            'bypass_csp': True,
            'ignore_https_errors': True
        }
        
        context = await browser.new_context(**context_options)
        context.set_default_timeout(60000)
        
        page = await context.new_page()
        
        await page.goto("https://www.youtube.com", timeout=60000, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)
        
        await subscribe_channel(page)
        await like_videos(page, num_videos=3)
        
        add_log(f"✓ Completed automation for account {account_num}", "success")
        return True
        
    except Exception as e:
        add_log(f"✗ Error processing account: {str(e)[:100]}", "error")
        return False
        
    finally:
        if page:
            try:
                await page.wait_for_timeout(2000)
            except:
                pass
        if context:
            try:
                await context.close()
            except:
                pass

# Streamlit UI
st.title("🎥 YouTube Multi-Account Automation Bot")
st.markdown("---")

# Account Selection Phase
if st.session_state.phase == 'account_selection':
    st.header("📊 Select Number of Accounts")
    st.write("How many YouTube accounts do you want to automate?")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("1 Account", use_container_width=True):
            st.session_state.num_accounts = 1
            st.session_state.phase = 'login_phase'
            st.rerun()
    
    with col2:
        if st.button("2 Accounts", use_container_width=True):
            st.session_state.num_accounts = 2
            st.session_state.phase = 'login_phase'
            st.rerun()
    
    with col3:
        if st.button("3 Accounts", use_container_width=True):
            st.session_state.num_accounts = 3
            st.session_state.phase = 'login_phase'
            st.rerun()
    
    col4, col5, col6 = st.columns(3)
    
    with col4:
        if st.button("4 Accounts", use_container_width=True):
            st.session_state.num_accounts = 4
            st.session_state.phase = 'login_phase'
            st.rerun()
    
    with col5:
        if st.button("5 Accounts", use_container_width=True):
            st.session_state.num_accounts = 5
            st.session_state.phase = 'login_phase'
            st.rerun()
    
    with col6:
        custom_num = st.number_input(
            "Custom:",
            min_value=6,
            max_value=20,
            value=6,
            key="custom_accounts_input"
        )
        if st.button("Use Custom", use_container_width=True):
            st.session_state.num_accounts = custom_num
            st.session_state.phase = 'login_phase'
            st.rerun()

# Login Phase
elif st.session_state.phase == 'login_phase':
    st.header("🔐 Phase 1: Login to Accounts")
    st.info(f"Total accounts selected: **{st.session_state.num_accounts}**")
    
    progress_text = f"Logging in account {st.session_state.current_login_account + 1} of {st.session_state.num_accounts}"
    progress_bar = st.progress(
        st.session_state.current_login_account / st.session_state.num_accounts,
        text=progress_text
    )
    
    if st.session_state.current_login_account < st.session_state.num_accounts:
        st.warning(f"⏳ Please login to Account {st.session_state.current_login_account + 1}")
        st.markdown("""
        **Instructions:**
        1. Click the button below to open the browser
        2. Login to your YouTube account manually
        3. Complete any 2FA if required
        4. Wait for the verification message
        5. The browser will automatically detect when you're logged in
        
        **Note:** If YouTube is slow to load, please be patient. The script has extended timeouts.
        """)
        
        if st.button(f"🚀 Login to Account {st.session_state.current_login_account + 1}", type="primary"):
            with st.spinner("Opening browser... Please complete login in the browser window"):
                async def do_login():
                    async with async_playwright() as p:
                        browser = await p.chromium.launch(
                            headless=False,
                            args=[
                                '--disable-blink-features=AutomationControlled',
                                '--start-maximized',
                                '--disable-web-security',
                                '--disable-features=IsolateOrigins,site-per-process'
                            ]
                        )
                        
                        success, session_file = await login_single_account(
                            browser,
                            st.session_state.current_login_account + 1,
                            st.session_state.num_accounts
                        )
                        
                        await browser.close()
                        
                        if success:
                            st.session_state.logged_in_accounts.append({
                                'account_num': st.session_state.current_login_account + 1,
                                'session_file': session_file
                            })
                            st.session_state.current_login_account += 1
                        
                        return success
                
                success = asyncio.run(do_login())
                
                if success:
                    st.success(f"✅ Account {st.session_state.current_login_account} logged in successfully!")
                else:
                    st.error(f"❌ Failed to login to account {st.session_state.current_login_account + 1}")
                
                st.rerun()
    else:
        st.success("✅ All accounts logged in successfully!")
        st.balloons()
        
        if st.button("▶️ Start Automation", type="primary", use_container_width=True):
            st.session_state.phase = 'automation_phase'
            st.rerun()

# Automation Phase
elif st.session_state.phase == 'automation_phase':
    st.header("🤖 Phase 2: Automating Accounts")
    st.info("The bot will now automatically subscribe, watch, and like videos for all logged-in accounts")
    
    if st.button("🎬 Start Automation", type="primary", use_container_width=True):
        # Create progress bar
        progress_bar = st.progress(0, text="Starting automation...")
        
        # Create live log placeholder
        st.subheader("📋 Live Activity Log")
        live_log_container = st.empty()
        st.session_state.live_log_placeholder = live_log_container
        
        async def run_automation():
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=False,
                    args=[
                        '--disable-blink-features=AutomationControlled',
                        '--start-maximized',
                        '--disable-web-security',
                        '--disable-features=IsolateOrigins,site-per-process'
                    ]
                )
                
                results = []
                
                for i, account_info in enumerate(st.session_state.logged_in_accounts):
                    progress = (i + 1) / len(st.session_state.logged_in_accounts)
                    progress_bar.progress(
                        progress,
                        text=f"Automating account {account_info['account_num']} of {len(st.session_state.logged_in_accounts)}"
                    )
                    
                    success = await automate_single_account(
                        browser,
                        account_info['account_num'],
                        len(st.session_state.logged_in_accounts),
                        account_info['session_file']
                    )
                    
                    results.append({
                        'account_num': account_info['account_num'],
                        'success': success
                    })
                    
                    if i < len(st.session_state.logged_in_accounts) - 1:
                        await asyncio.sleep(3)
                
                await browser.close()
                
                st.session_state.automation_results = results
                st.session_state.phase = 'completed'
                st.session_state.live_log_placeholder = None
                return results
        
        results = asyncio.run(run_automation())
        st.rerun()

# Completed Phase
elif st.session_state.phase == 'completed':
    st.header("🎉 Automation Complete!")
    
    successful = sum(1 for r in st.session_state.automation_results if r['success'])
    failed = len(st.session_state.automation_results) - successful
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Total Accounts", len(st.session_state.automation_results))
    
    with col2:
        st.metric("✅ Successful", successful)
    
    with col3:
        st.metric("❌ Failed", failed)
    
    st.markdown("---")
    st.subheader("Detailed Results")
    
    for result in st.session_state.automation_results:
        if result['success']:
            st.success(f"✅ Account {result['account_num']}: SUCCESS")
        else:
            st.error(f"❌ Account {result['account_num']}: FAILED")
    
    st.markdown("---")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("🔄 Start New Automation", use_container_width=True):
            st.session_state.phase = 'account_selection'
            st.session_state.current_login_account = 0
            st.session_state.logged_in_accounts = []
            st.session_state.automation_results = []
            st.session_state.logs = []
            st.rerun()
    
    with col2:
        if st.button("🗑️ Clear All Sessions", use_container_width=True, type="secondary"):
            try:
                import shutil
                if os.path.exists(SESSION_DIR):
                    shutil.rmtree(SESSION_DIR)
                    st.success("All saved sessions cleared!")
                    st.session_state.phase = 'account_selection'
                    st.session_state.current_login_account = 0
                    st.session_state.logged_in_accounts = []
                    st.session_state.automation_results = []
                    st.session_state.logs = []
                    st.rerun()
            except Exception as e:
                st.error(f"Error clearing sessions: {e}")

# Sidebar with logs
with st.sidebar:
    st.header("📋 Activity Log")
    
    if st.session_state.logs:
        for log in reversed(st.session_state.logs[-20:]):
            if log['type'] == 'success':
                st.success(f"[{log['time']}] {log['message']}", icon="✅")
            elif log['type'] == 'error':
                st.error(f"[{log['time']}] {log['message']}", icon="❌")
            elif log['type'] == 'warning':
                st.warning(f"[{log['time']}] {log['message']}", icon="⚠️")
            else:
                st.info(f"[{log['time']}] {log['message']}", icon="ℹ️")
    else:
        st.info("No activity yet")
    
    st.markdown("---")
    st.caption("YouTube Multi-Account Automation Bot v1.2")
    st.caption("💡 Real-time log updates enabled")