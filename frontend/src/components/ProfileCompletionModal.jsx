import React, { useState, useEffect } from 'react';
import { ShieldCheck, AlertTriangle, UserCheck, X } from 'lucide-react';
import { useAuth } from '../context/AuthContext';

export default function ProfileCompletionModal({ isOpen, onClose }) {
  const { user, updateUserProfile } = useAuth();

  const [name, setName] = useState('');
  const [age, setAge] = useState('');
  const [gender, setGender] = useState('Prefer not to say');
  const [consent, setConsent] = useState(false);
  const [minorConfirmed, setMinorConfirmed] = useState(false);
  const [errorMsg, setErrorMsg] = useState(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    if (user) {
      setName(user.name || '');
      setAge(user.age ? String(user.age) : '');
      setGender(user.gender || 'Prefer not to say');
      setConsent(Boolean(user.consent_timestamp));
      setMinorConfirmed(Boolean(user.minor_confirmed));
    }
  }, [user]);

  if (!isOpen) return null;

  const parsedAge = parseInt(age, 10);
  const isMinor = !isNaN(parsedAge) && parsedAge < 18 && parsedAge >= 1;

  const handleSubmit = async (e) => {
    e.preventDefault();
    setErrorMsg(null);

    // Validate name
    if (!name.trim()) {
      setErrorMsg('Full name is required.');
      return;
    }

    // Validate age
    if (isNaN(parsedAge) || parsedAge < 1 || parsedAge > 120) {
      setErrorMsg('Please enter a valid age between 1 and 120 years.');
      return;
    }

    // Validate minor confirmation
    if (isMinor && !minorConfirmed) {
      setErrorMsg('Explicit confirmation is required: This model has not been tested on children.');
      return;
    }

    // Validate consent
    if (!consent) {
      setErrorMsg('Consent to research prototype terms and privacy notice is mandatory.');
      return;
    }

    setIsSubmitting(true);
    try {
      await updateUserProfile({
        name: name.trim(),
        age: parsedAge,
        gender,
        consent,
        minor_confirmed: isMinor ? minorConfirmed : false
      });
      if (onClose) onClose();
    } catch (err) {
      setErrorMsg(err.message || 'Failed to update profile. Please check inputs.');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="modal-overlay">
      <div className="modal-card">
        <div className="modal-header">
          <div className="modal-title-group">
            <UserCheck size={20} className="text-teal" />
            <h3>Complete Researcher Profile</h3>
          </div>
          {user?.profile_complete && onClose && (
            <button type="button" className="btn-close" onClick={onClose} aria-label="Close">
              <X size={18} />
            </button>
          )}
        </div>

        <p className="modal-description">
          Please complete your basic profile before using the GPFormer forecasting tool. Your
          name, age, and gender are stored solely for session management and are <strong>never</strong> used as model inputs.
        </p>

        {errorMsg && (
          <div className="form-error-banner" role="alert">
            <AlertTriangle size={16} />
            <span>{errorMsg}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="modal-form">
          <div className="form-group">
            <label htmlFor="profile-name">
              Full Name <span className="text-danger">*</span>
            </label>
            <input
              id="profile-name"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="input-text"
              placeholder="e.g. Dr. Jane Research"
              required
            />
          </div>

          <div className="form-row">
            <div className="form-group flex-1">
              <label htmlFor="profile-age">
                Age in Years <span className="text-danger">*</span>
              </label>
              <input
                id="profile-age"
                type="number"
                min="1"
                max="120"
                value={age}
                onChange={(e) => setAge(e.target.value)}
                className="input-text"
                placeholder="1–120"
                required
              />
            </div>

            <div className="form-group flex-1">
              <label htmlFor="profile-gender">Gender (Optional)</label>
              <select
                id="profile-gender"
                value={gender}
                onChange={(e) => setGender(e.target.value)}
                className="input-select"
              >
                <option value="Female">Female</option>
                <option value="Male">Male</option>
                <option value="Non-binary">Non-binary</option>
                <option value="Other">Other</option>
                <option value="Prefer not to say">Prefer not to say</option>
              </select>
            </div>
          </div>

          {/* Prominent Under-18 Warning Banner */}
          {isMinor && (
            <div className="minor-warning-box">
              <div className="minor-warning-header">
                <AlertTriangle size={18} className="text-amber" />
                <strong>Pediatric Cohort Notice</strong>
              </div>
              <p className="minor-warning-text">
                This model has not been tested on children. Training was conducted exclusively on adult T1D
                and T2D cohorts (REPLACE-BG, Shanghai). Accuracy and safety in minors are unverified.
              </p>
              <label className="checkbox-label minor-check">
                <input
                  type="checkbox"
                  checked={minorConfirmed}
                  onChange={(e) => setMinorConfirmed(e.target.checked)}
                  required
                />
                <span>I confirm and understand that this model has not been tested on children.</span>
              </label>
            </div>
          )}

          {/* Research Consent Checkbox */}
          <div className="consent-box">
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={consent}
                onChange={(e) => setConsent(e.target.checked)}
                required
              />
              <span>
                I agree to the <a href="#privacy" onClick={(e) => e.preventDefault()} className="link-privacy">Privacy Notice</a> and
                acknowledge that this is a research prototype, not a medical device. Glucose forecasts
                must never be used for treatment decisions or insulin dosing.
              </span>
            </label>
          </div>

          <div className="modal-actions">
            <button
              type="submit"
              className="btn btn-primary"
              disabled={isSubmitting || !name.trim() || !age || (isMinor && !minorConfirmed) || !consent}
            >
              {isSubmitting ? 'Saving Profile...' : 'Save & Continue to App'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
