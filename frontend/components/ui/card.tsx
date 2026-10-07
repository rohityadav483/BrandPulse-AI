import * as React from 'react';import {cn} from '@/lib/utils';
export function Card({className,...props}:React.HTMLAttributes<HTMLDivElement>){return <div className={cn('rounded-xl border border-border bg-white shadow-card',className)} {...props}/>}
export function CardHeader({className,...props}:React.HTMLAttributes<HTMLDivElement>){return <div className={cn('p-5 pb-3',className)} {...props}/>}
export function CardTitle({className,...props}:React.HTMLAttributes<HTMLHeadingElement>){return <h2 className={cn('text-base font-semibold text-navy',className)} {...props}/>}
export function CardContent({className,...props}:React.HTMLAttributes<HTMLDivElement>){return <div className={cn('p-5 pt-2',className)} {...props}/>}
