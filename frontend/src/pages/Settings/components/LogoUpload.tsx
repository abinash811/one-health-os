/**
 * LogoUpload — drag & drop logo uploader with preview.
 * Converts file to base64 data URL and calls onChange.
 * No backend required — stored in pharmacy profile.
 */
import React, { useRef, useState } from 'react';
import { X, ImageIcon } from 'lucide-react';
import { AppButton } from '@/components/shared';

interface Props {
  value: string;           // current logo URL or base64
  onChange: (value: string) => void;
  label?: string;
}

export default function LogoUpload({ value, onChange, label = 'Pharmacy Logo' }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  const processFile = (file: File) => {
    if (!file.type.startsWith('image/')) return;
    const reader = new FileReader();
    reader.onload = (e) => onChange(e.target?.result as string);
    reader.readAsDataURL(file);
  };

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) processFile(file);
  };

  const onFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) processFile(file);
  };

  return (
    <div className="space-y-2">
      <p className="text-sm font-medium text-gray-700">{label}</p>

      {value ? (
        /* Preview state */
        <div className="relative inline-block">
          <img
            src={value}
            alt="Logo"
            className="h-20 w-auto max-w-[200px] object-contain rounded-lg border border-gray-200 bg-gray-50 p-2"
          />
          <AppButton
            type="button"
            variant="danger"
            iconOnly
            icon={<X className="w-3 h-3" />}
            onClick={() => onChange('')}
            className="absolute -top-2 -right-2 w-5 h-5 rounded-full p-0"
            aria-label="Remove image"
          />
          <AppButton
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => inputRef.current?.click()}
            className="mt-2 !h-auto !p-0 text-xs text-brand hover:underline"
          >
            Change
          </AppButton>
        </div>
      ) : (
        /* Drop zone */
        <div
          role="button"
          tabIndex={0}
          onClick={() => inputRef.current?.click()}
          onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); inputRef.current?.click(); } }}
          onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          className={`flex flex-col items-center justify-center gap-2 w-full h-28 rounded-xl border-2 border-dashed cursor-pointer transition-colors
            ${dragging
              ? 'border-brand bg-brand/5'
              : 'border-gray-200 bg-gray-50 hover:border-brand/40 hover:bg-brand/5'
            }`}
        >
          <div className="w-9 h-9 rounded-full bg-gray-100 flex items-center justify-center">
            <ImageIcon className="w-4 h-4 text-gray-400" />
          </div>
          <div className="text-center">
            <p className="text-xs font-medium text-gray-700">
              Drop image here or <span className="text-brand">browse</span>
            </p>
            <p className="text-[11px] text-gray-400 mt-0.5">PNG, JPG up to 2MB</p>
          </div>
        </div>
      )}

      <input
        ref={inputRef}
        type="file"
        accept="image/*"
        onChange={onFileChange}
        className="hidden"
      />
    </div>
  );
}
