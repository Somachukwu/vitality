import { logout } from './auth.js';
import { initLucide } from './utils.js';

const NAV = [
  { href: 'dashboard.html', label: 'Home', icon: 'home' },
  { href: 'food-log.html', label: 'Food', icon: 'utensils' },
  { href: 'vitals.html', label: 'Vitals', icon: 'activity' },
  { href: 'recommendations.html', label: 'Insights', icon: 'sparkles' },
  { href: 'profile.html', label: 'Profile', icon: 'user' },
];

export function renderNav(activeHref) {
  const bn = document.createElement('nav');
  bn.className = 'bottom-nav';
  bn.innerHTML = NAV.map(
    (n) => `<a href="${n.href}" class="${activeHref === n.href ? 'active' : ''}">
         <i data-lucide="${n.icon}"></i><span>${n.label}</span>
       </a>`
  ).join('');
  document.body.appendChild(bn);

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
