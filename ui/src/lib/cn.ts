import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/** Combine clsx + tailwind-merge so conditional className strings dedupe
 *  on conflicting Tailwind utilities. */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
