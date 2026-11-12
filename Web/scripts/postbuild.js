import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const distDir = path.resolve(__dirname, '../dist');
const indexPath = path.join(distDir, 'index.html');

if (fs.existsSync(indexPath)) {
  const routes = ['termsandservices', 'terms-and-services', 'terms'];
  for (const route of routes) {
    // 1. Root level .html (e.g. dist/termsandservices.html)
    fs.copyFileSync(indexPath, path.join(distDir, `${route}.html`));

    // 2. Directory with index.html (e.g. dist/termsandservices/index.html)
    const targetDir = path.join(distDir, route);
    if (!fs.existsSync(targetDir)) {
      fs.mkdirSync(targetDir, { recursive: true });
    }
    fs.copyFileSync(indexPath, path.join(targetDir, 'index.html'));
  }
  console.log('✓ Generated static SPA fallback files for:', routes.join(', '));
} else {
  console.warn('⚠️ Warning: dist/index.html not found, skipping fallback generation');
}

