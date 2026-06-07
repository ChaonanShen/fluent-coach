export default function ScenarioBriefingPanel({
  disabled,
  fileInputRef,
  knownInfoCharCount,
  knownInfoDocuments,
  knownInfoText,
  maxKnownInfoChars,
  onFileSelected,
  onKnownInfoTextChange,
  onRemoveDocument,
  onToggleOpen,
  open,
  selectedScenario,
  uploadError,
  uploadState,
}) {
  return (
    <section className={`scenario-briefing${open ? ' open' : ' collapsed'}`} aria-label="Scenario Briefing">
      <div className="scenario-briefing-header">
        <div>
          <h2>Scenario Briefing</h2>
          <p>
            {knownInfoCharCount.toLocaleString()} chars · {knownInfoDocuments.length} PDF
          </p>
        </div>
        <button
          className="secondary-action briefing-toggle"
          onClick={onToggleOpen}
          type="button"
        >
          {open ? 'Collapse' : 'Edit'}
        </button>
      </div>
      {open ? (
        <div className="scenario-briefing-body">
          <div className="briefing-scenario-meta">
            <span>{selectedScenario?.name || 'Custom'}</span>
            <span>{selectedScenario?.ai_role || 'AI role'}</span>
            <span>{selectedScenario?.conversation_goals?.length || 0} goals</span>
          </div>
          <label className="known-info-label">
            <span>Known Background</span>
            <textarea
              aria-label="Known background"
              disabled={disabled}
              maxLength={maxKnownInfoChars}
              onChange={(event) => onKnownInfoTextChange(event.target.value)}
              placeholder="Add resume highlights, meeting notes, preferences, or any context the AI should know before the conversation."
              rows={5}
              value={knownInfoText}
            />
          </label>
          <div className="briefing-upload-row">
            <input
              accept="application/pdf"
              aria-label="Upload briefing PDF"
              className="hidden-file-input"
              disabled={disabled || knownInfoDocuments.length >= 1 || uploadState === 'uploading'}
              onChange={(event) => onFileSelected(event.target.files?.[0])}
              ref={fileInputRef}
              type="file"
            />
            <button
              className="secondary-action"
              disabled={disabled || knownInfoDocuments.length >= 1 || uploadState === 'uploading'}
              onClick={() => fileInputRef.current?.click()}
              type="button"
            >
              {uploadState === 'uploading' ? 'Uploading' : 'Upload PDF'}
            </button>
            <span>{knownInfoDocuments.length ? '1 PDF attached' : 'No PDF attached'}</span>
          </div>
          {knownInfoDocuments.length ? (
            <div className="briefing-document-list">
              {knownInfoDocuments.map((document) => (
                <div className="briefing-document-chip" key={document.id}>
                  <span>{document.source.name}</span>
                  <small>{document.source.char_count.toLocaleString()} chars</small>
                  <button
                    aria-label={`Remove ${document.source.name}`}
                    className="icon-text-action"
                    disabled={disabled}
                    onClick={() => onRemoveDocument(document.id)}
                    type="button"
                  >
                    Remove
                  </button>
                </div>
              ))}
            </div>
          ) : null}
          {uploadError ? <p className="inline-error briefing-error">{uploadError}</p> : null}
        </div>
      ) : null}
    </section>
  );
}
