import { expect, it } from 'vitest';
import { translate } from './i18n.js';

it('keeps failure and privacy disclosures localized in Hindi and Telugu', () => {
  for (const [locale, script] of [['hi', /[\u0900-\u097f]/], ['te', /[\u0c00-\u0c7f]/]]) {
    for (const key of ['includeClosed', 'replyVisibility', 'failureQuota', 'failureTimeout', 'failureAuth', 'failureModel', 'failureSchema', 'failureNetwork', 'quotaRetry', 'photoNotice', 'photoHelp', 'clarificationHeading', 'clarificationHelp', 'answerClarification', 'typeInstead', 'cropCandidateReason', 'currentModelEstimate', 'weatherModelLimit', 'estimateTime']) {
      expect(translate(locale, key)).toMatch(script);
      expect(translate(locale, key)).not.toMatch(/\?\?\?/);
    }
    expect(translate(locale, 'photoNotice')).toContain('Google Gemini');
  }
});
