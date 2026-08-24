export function countUp(el, target, { duration = 900, decimals = 0, suffix = '' } = {}) {
  if (!el) return;
  const start = performance.now();
  function tick(now) {
    const t = Math.min(1, (now - start) / duration);
    const eased = 1 - Math.pow(1 - t, 3);
    el.textContent = (target * eased).toFixed(decimals) + suffix;
    if (t < 1) requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
}

export function vitalsStatus(metric, value) {
  if (value == null || Number.isNaN(value)) return 'unknown';
  switch (metric) {
    case 'heartRate':
      if (value < 50 || value > 120) return 'red';
      if (value < 60 || value > 100) return 'amber';
      return 'green';
    case 'spo2':
      if (value < 90) return 'red';
      if (value < 95) return 'amber';
      return 'green';
    case 'temperature':
      if (value > 38.0) return 'red';
      if (value < 36.1 || value > 37.5) return 'amber';
      return 'green';
    default: return 'green';
  }
}

export function statusDot(status, customLabel) {
  const label = customLabel ?? ({ green: 'Normal', amber: 'Borderline', red: 'Out of range', unknown: '—' }[status] || '');
  return `<span class="dot dot-${status}"></span><span class="text-xs muted">${label}</span>`;
}

export function computeBmi(weightKg, heightCm) {
  if (!weightKg || !heightCm) return null;
  const heightM = heightCm / 100;
  return weightKg / (heightM * heightM);
}

export function bmiStatus(bmi) {
  if (bmi == null || Number.isNaN(bmi)) return { status: 'unknown', label: '—' };
  if (bmi < 18.5) return { status: 'amber', label: 'Underweight' };
  if (bmi < 25)   return { status: 'green', label: 'Normal' };
  if (bmi < 30)   return { status: 'amber', label: 'Overweight' };
  return { status: 'red', label: 'Obese' };
}

export function formatDate(ts) {
  return new Date(ts).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}
export function formatTime(ts) {
  return new Date(ts).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
}
export function todayISO() { return new Date().toISOString().slice(0, 10); }

export function toast(msg, type = 'success') {
  let wrap = document.querySelector('.toast-wrap');
  if (!wrap) { wrap = document.createElement('div'); wrap.className = 'toast-wrap'; document.body.appendChild(wrap); }
  const t = document.createElement('div');
  t.className = `toast toast-${type}`;
  t.textContent = msg;
  wrap.appendChild(t);
  setTimeout(() => { t.style.opacity = '0'; t.style.transform = 'translateX(20px)'; }, 2400);
  setTimeout(() => t.remove(), 2700);
}

export function initLucide() { if (window.lucide) window.lucide.createIcons(); }
export function waitForChart(timeout = 350) {
  if (window.Chart) return Promise.resolve(true);
  const started = performance.now();
  return new Promise((resolve) => {
    const tick = () => {
      if (window.Chart) return resolve(true);
      if (performance.now() - started >= timeout) return resolve(false);
      setTimeout(tick, 50);
    };
    tick();
  });
}
export function applyStoredTheme() {
  if (localStorage.getItem('theme') === 'dark') document.documentElement.classList.add('dark');
}
export function toggleTheme() {
  const isDark = document.documentElement.classList.toggle('dark');
  localStorage.setItem('theme', isDark ? 'dark' : 'light');
}
export function initThemeToggle(btnId = 'theme-btn') {
  const btn = document.getElementById(btnId);
  if (btn) btn.addEventListener('click', toggleTheme);
}

export async function compressImage(file, maxDimension = 1920, quality = 0.85) {
  if (!file || !file.type.startsWith('image/')) return file;
  return new Promise((resolve) => {
    const img = new Image();
    const url = URL.createObjectURL(file);
    img.onload = () => {
      URL.revokeObjectURL(url);
      let { width, height } = img;
      if (width <= maxDimension && height <= maxDimension && file.size <= 1.5 * 1024 * 1024) {
        return resolve(file);
      }
      if (width > height) {
        if (width > maxDimension) {
          height = Math.round((height * maxDimension) / width);
          width = maxDimension;
        }
      } else {
        if (height > maxDimension) {
          width = Math.round((width * maxDimension) / height);
          height = maxDimension;
        }
      }
      const canvas = document.createElement('canvas');
      canvas.width = width;
      canvas.height = height;
      const ctx = canvas.getContext('2d');
      ctx.drawImage(img, 0, 0, width, height);
      canvas.toBlob(
        (blob) => {
          if (!blob) return resolve(file);
          const name = (file.name || 'photo.jpg').replace(/\.[^/.]+$/, '') + '.jpg';
          const compressedFile = new File([blob], name, { type: 'image/jpeg', lastModified: Date.now() });
          resolve(compressedFile);
        },
        'image/jpeg',
        quality
      );
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      resolve(file);
    };
    img.src = url;
  });
}

