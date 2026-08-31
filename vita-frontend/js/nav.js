import { logout } from './auth.js';
import { initLucide } from './utils.js';

export const NAV = [
  { href: 'dashboard.html', label: 'Home', icon: 'home' },
  { href: 'food-log.html', label: 'Food', icon: 'utensils' },
  { href: 'recommendations.html', label: 'Insights', icon: 'sparkles' },
  { href: 'goals.html', label: 'Goals', icon: 'target' },
  { href: 'vitals.html', label: 'Vitals', icon: 'activity' },
  { href: 'profile.html', label: 'Profile', icon: 'user' },
];

export function renderNav(activeHref) {
  // 1. Mobile Bottom Navigation with 3-bar Menu button
  const bn = document.createElement('nav');
  bn.className = 'bottom-nav';
  bn.innerHTML = `
    <a href="dashboard.html" class="${activeHref === 'dashboard.html' ? 'active' : ''}">
      <i data-lucide="home"></i><span>Home</span>
    </a>
    <a href="food-log.html" class="${activeHref === 'food-log.html' ? 'active' : ''}">
      <i data-lucide="utensils"></i><span>Food</span>
    </a>
    <a href="recommendations.html" class="${activeHref === 'recommendations.html' ? 'active' : ''}">
      <i data-lucide="sparkles"></i><span>Insights</span>
    </a>
    <a href="goals.html" class="${activeHref === 'goals.html' ? 'active' : ''}">
      <i data-lucide="target"></i><span>Goals</span>
    </a>
    <button type="button" class="mobile-menu-trigger" id="mobile-menu-btn" aria-label="Open menu">
      <i data-lucide="menu"></i><span>Menu</span>
    </button>
  `;
  document.body.appendChild(bn);


  // 2. Mobile Drawer Overlay Modal
  const drawerOverlay = document.createElement('div');
  drawerOverlay.className = 'mobile-drawer-overlay';
  drawerOverlay.id = 'mobile-drawer-overlay';
  drawerOverlay.innerHTML = `
    <div class="mobile-drawer" id="mobile-drawer">
      <div class="row between align-center mb-3">
        <div class="brand">
          <img src="vitality-logo-icon.png" class="brand-logo" style="height:32px" alt="Vitality"/>
          <span>Vitality</span>
        </div>
        <button class="btn btn-ghost mobile-drawer-close" id="mobile-drawer-close" aria-label="Close menu">
          <i data-lucide="x"></i>
        </button>
      </div>
      <div class="mobile-drawer-links stack mb-3" style="gap:0.35rem">
        ${NAV.map(
          (n) => `<a href="${n.href}" class="mobile-nav-link ${activeHref === n.href ? 'active' : ''}">
               <i data-lucide="${n.icon}"></i><span>${n.label}</span>
             </a>`
        ).join('')}
      </div>
      <div style="margin-top:auto; border-top:1px solid var(--border); padding-top:1rem">
        <button class="btn btn-ghost w-full" id="mobile-drawer-logout" style="width:100%; justify-content:center; color:#ef4444">
          <i data-lucide="log-out"></i> Log out
        </button>
      </div>
    </div>
  `;
  document.body.appendChild(drawerOverlay);

  // Drawer Open / Close Handlers
  const openDrawer = () => {
    drawerOverlay.classList.add('open');
    document.body.style.overflow = 'hidden';
  };
  const closeDrawer = () => {
    drawerOverlay.classList.remove('open');
    document.body.style.overflow = '';
  };

  const menuBtn = document.getElementById('mobile-menu-btn');
  if (menuBtn) menuBtn.addEventListener('click', openDrawer);

  const closeBtn = document.getElementById('mobile-drawer-close');
  if (closeBtn) closeBtn.addEventListener('click', closeDrawer);

  // Close when clicking outside drawer
  drawerOverlay.addEventListener('click', (e) => {
    if (e.target === drawerOverlay) closeDrawer();
  });

  // Automatically close drawer when any navigation link is selected
  drawerOverlay.querySelectorAll('.mobile-nav-link').forEach((link) => {
    link.addEventListener('click', closeDrawer);
  });

  const drawerLogout = document.getElementById('mobile-drawer-logout');
  if (drawerLogout) drawerLogout.addEventListener('click', logout);

  // 3. Desktop Sidebar Navigation
  const sideHost = document.querySelector('.side-nav');
  if (sideHost) {
    sideHost.innerHTML = `
      <div class="brand mb-3"><img src="vitality-logo-icon.png" class="brand-logo" alt="Vitality"/><span>Vitality</span></div>
      ${NAV.map(
        (n) => `<a href="${n.href}" class="${activeHref === n.href ? 'active' : ''}">
             <i data-lucide="${n.icon}"></i><span>${n.label}</span>
           </a>`
      ).join('')}
      <button class="btn btn-ghost" id="side-logout" style="margin-top:auto"><i data-lucide="log-out"></i>Log out</button>
    `;
    sideHost.querySelector('#side-logout').addEventListener('click', logout);
  }

  initLucide();
}

