import { Geist, Geist_Mono, Noto_Sans_KR } from "next/font/google";

/*
 * Studio fonts (self-hosted by next/font: downloaded at build time, served from this app, so the
 * browser never contacts Google). Only the Studio root uses them; Classic keeps system fonts.
 * Geist covers Latin UI text; Hangul falls through to Noto Sans KR, whose many unicode-range
 * slices load only as needed (no preload). The CSS stacks live in globals.css (Studio block).
 */
export const studioSans = Geist({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-studio-sans",
});

export const studioMono = Geist_Mono({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-studio-mono",
});

export const studioKorean = Noto_Sans_KR({
  preload: false,
  display: "swap",
  variable: "--font-studio-kr",
});

/** Class names that define the three font variables on an element. */
export const studioFontVariables = [
  studioSans.variable,
  studioMono.variable,
  studioKorean.variable,
].join(" ");
