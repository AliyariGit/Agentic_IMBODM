package com.bank.odm.model;

import java.util.List;

/**
 * BOM output class — returned by the ruleflow and serialized to JSON by HTDS.
 * Rules write to this object; the REST endpoint returns it directly.
 */
public class AuthorizationResponse {

    private String decision;             // APPROVED | DECLINED
    private String responseCode;         // ISO 8583 (00 = approved, 05 = declined)
    private String authorizationCode;    // 6-char alphanumeric, null if declined
    private String declineReason;        // Human-readable, null if approved
    private List<RuleTrace> auditTrail;  // One entry per fired rule

    public static class RuleTrace {
        private String ruleName;
        private boolean fired;
        private String result;   // PASS | DECLINED
        private String message;

        public String getRuleName() { return ruleName; }
        public void setRuleName(String ruleName) { this.ruleName = ruleName; }

        public boolean isFired() { return fired; }
        public void setFired(boolean fired) { this.fired = fired; }

        public String getResult() { return result; }
        public void setResult(String result) { this.result = result; }

        public String getMessage() { return message; }
        public void setMessage(String message) { this.message = message; }
    }

    public String getDecision() { return decision; }
    public void setDecision(String decision) { this.decision = decision; }

    public String getResponseCode() { return responseCode; }
    public void setResponseCode(String responseCode) { this.responseCode = responseCode; }

    public String getAuthorizationCode() { return authorizationCode; }
    public void setAuthorizationCode(String authorizationCode) { this.authorizationCode = authorizationCode; }

    public String getDeclineReason() { return declineReason; }
    public void setDeclineReason(String declineReason) { this.declineReason = declineReason; }

    public List<RuleTrace> getAuditTrail() { return auditTrail; }
    public void setAuditTrail(List<RuleTrace> auditTrail) { this.auditTrail = auditTrail; }
}
