import { useState, useCallback, useRef } from 'react';
import Cropper from 'react-easy-crop';
import { useLanguage } from '../i18n/LanguageContext';

const ASPECT_RATIOS = [
  { label: '1:1', value: 1, key: 'square' },
  { label: '4:5', value: 4 / 5, key: 'portrait' },
  { label: '16:9', value: 16 / 9, key: 'landscape' },
];

function getCroppedImg(imageSrc, pixelCrop) {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => {
      const canvas = document.createElement('canvas');
      canvas.width = pixelCrop.width;
      canvas.height = pixelCrop.height;
      const ctx = canvas.getContext('2d');

      const scaleX = image.naturalWidth / image.width;
      const scaleY = image.naturalHeight / image.height;

      ctx.drawImage(
        image,
        pixelCrop.x * scaleX,
        pixelCrop.y * scaleY,
        pixelCrop.width * scaleX,
        pixelCrop.height * scaleY,
        0,
        0,
        pixelCrop.width,
        pixelCrop.height
      );

      canvas.toBlob(
        (blob) => {
          if (!blob) {
            reject(new Error('Canvas is empty'));
            return;
          }
          blob.name = 'cropped.jpg';
          resolve(blob);
        },
        'image/jpeg',
        0.92
      );
    };
    image.onerror = (err) => reject(err);
    image.src = imageSrc;
  });
}

function CropModal({ imageUrl, originalName, onCancel, onApply }) {
  const { t } = useLanguage();
  const [crop, setCrop] = useState({ x: 0, y: 0 });
  const [zoom, setZoom] = useState(1);
  const [aspect, setAspect] = useState(1);
  const [croppedAreaPixels, setCroppedAreaPixels] = useState(null);
  const [processing, setProcessing] = useState(false);
  const imageUrlRef = useRef(imageUrl);

  const onCropComplete = useCallback((croppedArea, croppedAreaPixels) => {
    setCroppedAreaPixels(croppedAreaPixels);
  }, []);

  const handleApply = async () => {
    if (!croppedAreaPixels) return;
    setProcessing(true);
    try {
      const blob = await getCroppedImg(imageUrlRef.current, croppedAreaPixels);
      onApply(blob);
    } catch (err) {
      console.error('Crop failed:', err);
      setProcessing(false);
    }
  };

  return (
    <div className="crop-modal-overlay" onClick={onCancel}>
      <div className="crop-modal" onClick={(e) => e.stopPropagation()}>
        <div className="crop-modal-header">
          <h4>{t('cropModal.title')}</h4>
          <span className="crop-file-name">{originalName}</span>
        </div>

        <div className="crop-area">
          <Cropper
            image={imageUrl}
            crop={crop}
            zoom={zoom}
            aspect={aspect}
            onCropChange={setCrop}
            onZoomChange={setZoom}
            onCropComplete={onCropComplete}
            showGrid
          />
        </div>

        <div className="crop-controls">
          <label>{t('cropModal.zoom')}</label>
          <input
            type="range"
            min={1}
            max={3}
            step={0.01}
            value={zoom}
            onChange={(e) => setZoom(Number(e.target.value))}
            className="crop-zoom-slider"
          />
        </div>

        <div className="crop-aspect-row">
          {ASPECT_RATIOS.map((ratio) => (
            <button
              key={ratio.label}
              className={`crop-aspect-btn ${aspect === ratio.value ? 'active' : ''}`}
              onClick={() => setAspect(ratio.value)}
            >
              <span className="crop-aspect-label">{ratio.label}</span>
              <span className="crop-aspect-sub">{t('cropModal.' + ratio.key)}</span>
            </button>
          ))}
        </div>

        <div className="crop-modal-actions">
          <button className="btn btn-outline" onClick={onCancel} disabled={processing}>
            {t('cropModal.cancel')}
          </button>
          <button className="btn bg-gradient-to-r from-fuchsia-400/10 to-fuchsia-400/10 text-fuchsia-100 border border-fuchsia-500/30 transition-all duration-200 ease-out hover:from-fuchsia-400/20 hover:to-fuchsia-400/20 hover:border-fuchsia-400/50 hover:shadow-[0_0_22px_rgba(45,212,191,0.25)] active:scale-95" onClick={handleApply} disabled={processing}>
            {processing ? <><span className="spinner-sm" /> {t('cropModal.applying')}</> : t('cropModal.apply')}
          </button>
        </div>
      </div>
    </div>
  );
}

export default CropModal;