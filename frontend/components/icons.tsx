import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement> & { size?: number };

function IconBase({ size = 20, children, ...props }: IconProps) {
  return (
    <svg aria-hidden="true" fill="none" height={size} viewBox="0 0 24 24" width={size} {...props}>
      {children}
    </svg>
  );
}

export function LibraryIcon(props: IconProps) {
  return (
    <IconBase {...props}>
      <path
        d="M4 4.5h3v15H4zM9.5 4.5h3v15h-3zM15 5.5l2.9-.8 3.9 14.5-2.9.8z"
        stroke="currentColor"
        strokeWidth="1.7"
      />
    </IconBase>
  );
}

export function UploadIcon(props: IconProps) {
  return (
    <IconBase {...props}>
      <path
        d="M12 16V4m0 0L7.5 8.5M12 4l4.5 4.5M5 14.5V20h14v-5.5"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="1.8"
      />
    </IconBase>
  );
}

export function LinkIcon(props: IconProps) {
  return (
    <IconBase {...props}>
      <path
        d="M9.5 14.5l5-5M7.2 16.8l-1.5 1.5a3.5 3.5 0 01-5-5l3-3a3.5 3.5 0 015 0M16.8 7.2l1.5-1.5a3.5 3.5 0 015 5l-3 3a3.5 3.5 0 01-5 0"
        stroke="currentColor"
        strokeLinecap="round"
        strokeWidth="1.8"
      />
    </IconBase>
  );
}

export function SearchIcon(props: IconProps) {
  return (
    <IconBase {...props}>
      <circle cx="10.8" cy="10.8" r="6.3" stroke="currentColor" strokeWidth="1.8" />
      <path d="M15.5 15.5L20 20" stroke="currentColor" strokeLinecap="round" strokeWidth="1.8" />
    </IconBase>
  );
}

export function MessageIcon(props: IconProps) {
  return (
    <IconBase {...props}>
      <path
        d="M4 5.5h16v11H9l-5 4z"
        stroke="currentColor"
        strokeLinejoin="round"
        strokeWidth="1.8"
      />
      <path d="M8 9.5h8M8 12.5h5" stroke="currentColor" strokeLinecap="round" strokeWidth="1.6" />
    </IconBase>
  );
}

export function TranscriptIcon(props: IconProps) {
  return (
    <IconBase {...props}>
      <path
        d="M6 3.5h9l3 3V20.5H6z"
        stroke="currentColor"
        strokeLinejoin="round"
        strokeWidth="1.7"
      />
      <path
        d="M15 3.5v3h3M9 10h6M9 13.5h6M9 17h4"
        stroke="currentColor"
        strokeLinecap="round"
        strokeWidth="1.6"
      />
    </IconBase>
  );
}

export function SummaryIcon(props: IconProps) {
  return (
    <IconBase {...props}>
      <path
        d="M4.5 5.5h15M4.5 10h15M4.5 14.5h10M4.5 19h7"
        stroke="currentColor"
        strokeLinecap="round"
        strokeWidth="1.8"
      />
    </IconBase>
  );
}

export function ArrowIcon(props: IconProps) {
  return (
    <IconBase {...props}>
      <path
        d="M5 12h14M14 7l5 5-5 5"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="1.8"
      />
    </IconBase>
  );
}

export function ChevronLeftIcon(props: IconProps) {
  return (
    <IconBase {...props}>
      <path
        d="M14.5 5L7.5 12l7 7"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="1.8"
      />
    </IconBase>
  );
}

export function ExternalIcon(props: IconProps) {
  return (
    <IconBase {...props}>
      <path
        d="M13 5h6v6M19 5l-8 8M17 13v6H5V7h6"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="1.7"
      />
    </IconBase>
  );
}

export function SparkIcon(props: IconProps) {
  return (
    <IconBase {...props}>
      <path
        d="M12 2.8l1.3 4.1L17.2 8l-3.9 1.2L12 13.3l-1.3-4.1L6.8 8l3.9-1.1zM18.5 13.5l.7 2.2 2.1.7-2.1.7-.7 2.2-.7-2.2-2.1-.7 2.1-.7zM5.3 14.8l.8 2.5 2.4.8-2.4.7-.8 2.5-.8-2.5-2.4-.7 2.4-.8z"
        fill="currentColor"
      />
    </IconBase>
  );
}

export function CheckIcon(props: IconProps) {
  return (
    <IconBase {...props}>
      <path
        d="M5 12.5l4.2 4.2L19 7"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="1.9"
      />
    </IconBase>
  );
}

export function ClockIcon(props: IconProps) {
  return (
    <IconBase {...props}>
      <circle cx="12" cy="12" r="8.5" stroke="currentColor" strokeWidth="1.7" />
      <path d="M12 7v5l3.5 2" stroke="currentColor" strokeLinecap="round" strokeWidth="1.7" />
    </IconBase>
  );
}

export function AlertIcon(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="M12 3l9 17H3z" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.7" />
      <path d="M12 9v5M12 17.2v.1" stroke="currentColor" strokeLinecap="round" strokeWidth="1.9" />
    </IconBase>
  );
}

export function SendIcon(props: IconProps) {
  return (
    <IconBase {...props}>
      <path
        d="M3.5 4l17 8-17 8 2.3-6.1L14 12l-8.2-1.9z"
        stroke="currentColor"
        strokeLinejoin="round"
        strokeWidth="1.7"
      />
    </IconBase>
  );
}

export function EditIcon(props: IconProps) {
  return (
    <IconBase {...props}>
      <path
        d="M5 19l3.5-.8L19 6.7 16.3 4 4.8 15.5zM14.8 5.5l2.7 2.7"
        stroke="currentColor"
        strokeLinejoin="round"
        strokeWidth="1.7"
      />
    </IconBase>
  );
}

export function DownloadIcon(props: IconProps) {
  return (
    <IconBase {...props}>
      <path
        d="M12 4v11m0 0l-4-4m4 4l4-4M5 19.5h14"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="1.8"
      />
    </IconBase>
  );
}
