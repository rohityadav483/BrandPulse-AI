import * as React from 'react';import {cn} from '@/lib/utils';
export function Button({className,...props}:React.ButtonHTMLAttributes<HTMLButtonElement>){return <button className={cn('inline-flex items-center justify-center rounded-lg bg-brand px-4 py-2 text-sm font-semibold text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50',className)} {...props}/>}
