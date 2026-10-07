/** @type {import('next').NextConfig} */
module.exports={reactStrictMode:true,async rewrites(){const apiOrigin=process.env.API_ORIGIN||'http://127.0.0.1:8000';return[{source:'/api/:path*',destination:`${apiOrigin}/api/:path*`}];}};
