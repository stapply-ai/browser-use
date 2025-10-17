"""About:blank watchdog for managing about:blank tabs with DVD screensaver."""

from typing import TYPE_CHECKING, ClassVar

from bubus import BaseEvent
from cdp_use.cdp.target import TargetID
from pydantic import PrivateAttr

from browser_use.browser.events import (
	AboutBlankDVDScreensaverShownEvent,
	BrowserStopEvent,
	BrowserStoppedEvent,
	CloseTabEvent,
	NavigateToUrlEvent,
	TabClosedEvent,
	TabCreatedEvent,
)
from browser_use.browser.watchdog_base import BaseWatchdog

if TYPE_CHECKING:
	pass


class AboutBlankWatchdog(BaseWatchdog):
	"""Ensures there's always exactly one about:blank tab with DVD screensaver."""

	# Event contracts
	LISTENS_TO: ClassVar[list[type[BaseEvent]]] = [
		BrowserStopEvent,
		BrowserStoppedEvent,
		TabCreatedEvent,
		TabClosedEvent,
	]
	EMITS: ClassVar[list[type[BaseEvent]]] = [
		NavigateToUrlEvent,
		CloseTabEvent,
		AboutBlankDVDScreensaverShownEvent,
	]

	_stopping: bool = PrivateAttr(default=False)

	async def on_BrowserStopEvent(self, event: BrowserStopEvent) -> None:
		"""Handle browser stop request - stop creating new tabs."""
		# logger.info('[AboutBlankWatchdog] Browser stop requested, stopping tab creation')
		self._stopping = True

	async def on_BrowserStoppedEvent(self, event: BrowserStoppedEvent) -> None:
		"""Handle browser stopped event."""
		# logger.info('[AboutBlankWatchdog] Browser stopped')
		self._stopping = True

	async def on_TabCreatedEvent(self, event: TabCreatedEvent) -> None:
		"""Check tabs when a new tab is created."""
		# logger.debug(f'[AboutBlankWatchdog] ➕ New tab created: {event.url}')

		# If an about:blank tab was created, show DVD screensaver on all about:blank tabs
		if event.url == 'about:blank':
			await self._show_dvd_screensaver_on_about_blank_tabs()

	async def on_TabClosedEvent(self, event: TabClosedEvent) -> None:
		"""Check tabs when a tab is closed and proactively create about:blank if needed."""
		# logger.debug('[AboutBlankWatchdog] Tab closing, checking if we need to create about:blank tab')

		# Don't create new tabs if browser is shutting down
		if self._stopping:
			# logger.debug('[AboutBlankWatchdog] Browser is stopping, not creating new tabs')
			return

		# Check if we're about to close the last tab (event happens BEFORE tab closes)
		# Use _cdp_get_all_pages for quick check without fetching titles
		page_targets = await self.browser_session._cdp_get_all_pages()
		if len(page_targets) <= 1:
			self.logger.debug(
				'[AboutBlankWatchdog] Last tab closing, creating new about:blank tab to avoid closing entire browser'
			)
			# Create the animation tab since no tabs should remain
			navigate_event = self.event_bus.dispatch(NavigateToUrlEvent(url='about:blank', new_tab=True))
			await navigate_event
			# Show DVD screensaver on the new tab
			await self._show_dvd_screensaver_on_about_blank_tabs()
		else:
			# Multiple tabs exist, check after close
			await self._check_and_ensure_about_blank_tab()

	async def attach_to_target(self, target_id: TargetID) -> None:
		"""AboutBlankWatchdog doesn't monitor individual targets."""
		pass

	async def _check_and_ensure_about_blank_tab(self) -> None:
		"""Check current tabs and ensure exactly one about:blank tab with animation exists."""
		try:
			# For quick checks, just get page targets without titles to reduce noise
			page_targets = await self.browser_session._cdp_get_all_pages()

			# If no tabs exist at all, create one to keep browser alive
			if len(page_targets) == 0:
				# Only create a new tab if there are no tabs at all
				self.logger.debug('[AboutBlankWatchdog] No tabs exist, creating new about:blank DVD screensaver tab')
				navigate_event = self.event_bus.dispatch(NavigateToUrlEvent(url='about:blank', new_tab=True))
				await navigate_event
				# Show DVD screensaver on the new tab
				await self._show_dvd_screensaver_on_about_blank_tabs()
			# Otherwise there are tabs, don't create new ones to avoid interfering

		except Exception as e:
			self.logger.error(f'[AboutBlankWatchdog] Error ensuring about:blank tab: {e}')

	async def _show_dvd_screensaver_on_about_blank_tabs(self) -> None:
		"""Show DVD screensaver on all about:blank pages only."""
		try:
			# Get just the page targets without expensive title fetching
			page_targets = await self.browser_session._cdp_get_all_pages()
			browser_session_label = str(self.browser_session.id)[-4:]

			for page_target in page_targets:
				target_id = page_target['targetId']
				url = page_target['url']

				# Only target about:blank pages specifically
				if url == 'about:blank':
					await self._show_dvd_screensaver_loading_animation_cdp(target_id, browser_session_label)

		except Exception as e:
			self.logger.error(f'[AboutBlankWatchdog] Error showing DVD screensaver: {e}')

	async def _show_dvd_screensaver_loading_animation_cdp(self, target_id: TargetID, browser_session_label: str) -> None:
		"""
		Injects a DVD screensaver-style bouncing logo loading animation overlay into the target using CDP.
		This is used to visually indicate that the browser is setting up or waiting.
		"""
		try:
			# Create temporary session for this target without switching focus
			temp_session = await self.browser_session.get_or_create_cdp_session(target_id, focus=False)

			# Inject the DVD screensaver script (from main branch with idempotency added)
			script = f"""
				(function(browser_session_label) {{
					// Idempotency check
					if (window.__dvdAnimationRunning) {{
						return; // Already running, don't add another
					}}
					window.__dvdAnimationRunning = true;
					
					// Ensure document.body exists before proceeding
					if (!document.body) {{
						// Try again after DOM is ready
						window.__dvdAnimationRunning = false; // Reset flag to retry
						if (document.readyState === 'loading') {{
							document.addEventListener('DOMContentLoaded', () => arguments.callee(browser_session_label));
						}}
						return;
					}}
					
					const animated_title = `Starting Agent Stapply...`;
					if (document.title === animated_title) {{
						return;      // already run on this tab, dont run again
					}}
					document.title = animated_title;

						// Create the main overlay
						const loadingOverlay = document.createElement('div');
						loadingOverlay.id = 'pretty-loading-animation';
						loadingOverlay.style.position = 'fixed';
						loadingOverlay.style.top = '0';
						loadingOverlay.style.left = '0';
						loadingOverlay.style.width = '100vw';
						loadingOverlay.style.height = '100vh';
						loadingOverlay.style.background = 'radial-gradient(1200px 800px at 20% 20%, #0f172a 0%, #0b1023 40%, #050814 70%, #000 100%)';
						loadingOverlay.style.zIndex = '99999';
						loadingOverlay.style.overflow = 'hidden';
						loadingOverlay.style.opacity = '0';
						loadingOverlay.style.transition = 'opacity 300ms ease-out';

					// Create the image element
					const img = document.createElement('img');
					img.src = 'https://storage.stapply.ai/assets/stapply_white.svg';
					img.alt = 'Agent Stapply';
					img.style.width = '200px';
					img.style.height = 'auto';
					img.style.position = 'absolute';
					img.style.left = '0px';
					img.style.top = '0px';
					img.style.zIndex = '2';
						img.style.opacity = '0.9';
						img.style.filter = 'drop-shadow(0 6px 24px rgba(255,255,255,0.12)) drop-shadow(0 2px 8px rgba(80,160,255,0.25))';

					// Create the text element (center bottom of the screen, always visible, above the image)
					const text = document.createElement('div');
					text.id = 'powered-by';
					text.textContent = 'powered by Browser-Use';
					text.style.color = '#fff';
						text.style.fontSize = '14px';
						text.style.letterSpacing = '0.04em';
						text.style.fontFamily = 'ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Ubuntu, Cantarell, Noto Sans, Helvetica Neue, Arial, Apple Color Emoji, Segoe UI Emoji';
					text.style.textAlign = 'center';
					text.style.position = 'absolute';
						text.style.bottom = '20px';
					text.style.left = '50%';
					text.style.transform = 'translateX(-50%)';
					text.style.zIndex = '3';
						text.style.opacity = '0.85';

						// Create the Browser-Use logo element (bottom center, above the image)
					const browserUseLogo = document.createElement('img');
					browserUseLogo.id = 'browseruse-logo';
					browserUseLogo.src = 'https://cf.browser-use.com/logo.svg';
					browserUseLogo.alt = 'Browser-Use';
						browserUseLogo.style.width = '90px';
					browserUseLogo.style.height = 'auto';
					browserUseLogo.style.position = 'absolute';
						browserUseLogo.style.left = '50%';
						browserUseLogo.style.bottom = '48px';
						browserUseLogo.style.transform = 'translateX(-50%)';
					browserUseLogo.style.zIndex = '3';
						browserUseLogo.style.opacity = '0.9';
						browserUseLogo.style.filter = 'drop-shadow(0 4px 16px rgba(80,160,255,0.35))';

					loadingOverlay.appendChild(img);
					loadingOverlay.appendChild(text);
					loadingOverlay.appendChild(browserUseLogo);

						document.body.appendChild(loadingOverlay);
						// Fade-in
						requestAnimationFrame(() => {{ loadingOverlay.style.opacity = '1'; }});



					// DVD screensaver bounce logic with bottom safe area to avoid branding overlap
					let x = Math.random() * (window.innerWidth - 300);
					let y = Math.random() * (window.innerHeight - 300);
					let dx = 1.2 + Math.random() * 0.4; // px per frame
					let dy = 1.2 + Math.random() * 0.4;
					// Randomize direction
					if (Math.random() > 0.5) dx = -dx;
					if (Math.random() > 0.5) dy = -dy;

					function getBounds(w, h) {{
						const margin = 8; // small breathing room
						const textEl = document.getElementById('powered-by');
						const logoEl = document.getElementById('browseruse-logo');
						const textRect = textEl ? textEl.getBoundingClientRect() : null;
						const logoRect = logoEl ? logoEl.getBoundingClientRect() : null;
						let bottomSafeTop = window.innerHeight;
						if (textRect) bottomSafeTop = Math.min(bottomSafeTop, textRect.top);
						if (logoRect) bottomSafeTop = Math.min(bottomSafeTop, logoRect.top);
						const maxX = Math.max(0, window.innerWidth - w);
						const maxY = Math.max(0, bottomSafeTop - h - margin);
						return {{ maxX, maxY }};
					}}

					function animate() {{
						const imgWidth = img.offsetWidth || 300;
						const imgHeight = img.offsetHeight || 300;
						const {{ maxX, maxY }} = getBounds(imgWidth, imgHeight);
						x += dx;
						y += dy;

						if (x <= 0) {{
							x = 0;
							dx = Math.abs(dx);
						}} else if (x >= maxX) {{
							x = maxX;
							dx = -Math.abs(dx);
						}}
						if (y <= 0) {{
							y = 0;
							dy = Math.abs(dy);
						}} else if (y >= maxY) {{
							y = maxY;
							dy = -Math.abs(dy);
						}}

						img.style.left = `${{x}}px`;
						img.style.top = `${{y}}px`;

						requestAnimationFrame(animate);
					}}
					// Ensure initial position respects bounds
					(function initPosition() {{
						const w = img.offsetWidth || 300;
						const h = img.offsetHeight || 300;
						const {{ maxX, maxY }} = getBounds(w, h);
						x = Math.min(Math.max(0, x), maxX);
						y = Math.min(Math.max(0, y), maxY);
					}})();
					animate();

					// Responsive: update bounds on resize
					window.addEventListener('resize', () => {{
						const w = img.offsetWidth || 300;
						const h = img.offsetHeight || 300;
						const {{ maxX, maxY }} = getBounds(w, h);
						x = Math.min(x, maxX);
						y = Math.min(y, maxY);
					}});

						// Add a little CSS for smoothness and subtle décor
					const style = document.createElement('style');
					style.textContent = `
						#pretty-loading-animation {{
								/*backdrop-filter: blur(2px) brightness(0.9);*/
								position: fixed;
								inset: 0;
							}}
							#pretty-loading-animation::before {{
								content: '';
								position: absolute;
								inset: 0;
								background: radial-gradient(600px 400px at 80% 80%, rgba(80,160,255,0.12) 0%, rgba(80,160,255,0.04) 40%, transparent 70%)
									, radial-gradient(800px 600px at 10% 10%, rgba(255,255,255,0.08) 0%, rgba(255,255,255,0.03) 35%, transparent 70%);
								pointer-events: none;
								z-index: 1;
						}}
						#pretty-loading-animation img {{
							user-select: none;
							pointer-events: none;
						}}
							@media (max-width: 640px) {{
								#pretty-loading-animation img {{ width: 140px !important; }}
							}}
					`;
					document.head.appendChild(style);
				}})('{browser_session_label}');
			"""

			await temp_session.cdp_client.send.Runtime.evaluate(params={'expression': script}, session_id=temp_session.session_id)

			# No need to detach - session is cached

			# Dispatch event
			self.event_bus.dispatch(AboutBlankDVDScreensaverShownEvent(target_id=target_id))

		except Exception as e:
			self.logger.error(f'[AboutBlankWatchdog] Error injecting DVD screensaver: {e}')
