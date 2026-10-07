import type { Config } from 'tailwindcss';
const config:Config={content:['./app/**/*.{ts,tsx}','./components/**/*.{ts,tsx}','./lib/**/*.{ts,tsx}'],theme:{extend:{colors:{navy:'#0f2747',brand:'#2563eb','brand-soft':'#eff6ff',border:'#dbe5f1'},boxShadow:{card:'0 1px 3px rgba(15,39,71,0.06),0 8px 24px rgba(15,39,71,0.04)'}}},plugins:[]};
export default config;
