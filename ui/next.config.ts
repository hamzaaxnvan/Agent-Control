import type { NextConfig } from 'next';

const isStaticExport = process.env.AGENT_CONTROL_STATIC_EXPORT === 'true';
const shouldUnoptimizeImages = isStaticExport || Boolean(process.env.CI);

const nextConfig: NextConfig = {
  pageExtensions: ['tsx', 'ts', 'jsx', 'js'],
  reactStrictMode: true,
  ...(isStaticExport && {
    output: 'export',
    trailingSlash: true,
  }),
  ...(shouldUnoptimizeImages && {
    images: {
      unoptimized: true,
    },
