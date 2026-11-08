export type Metadata = {
  title?: string | { default: string; template: string };
  description?: string;
  robots?: { index: boolean; follow: boolean };
  alternates?: { canonical: string };
  openGraph?: {
    type?: string; siteName?: string; locale?: string; title?: string;
    description?: string; url?: string; publishedTime?: string;
    images?: { url: string; width: number; height: number; alt: string }[];
  };
};
export type Assets = { script: string; stylesheet: string };
