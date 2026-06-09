package com.bank.odm.rest;

import com.bank.odm.model.AuthorizationResponse;
import com.bank.odm.model.TransactionRequest;
import ilog.rules.res.session.IlrJ2SESessionFactory;
import ilog.rules.res.session.IlrStatelessSession;
import ilog.rules.res.session.IlrSessionRequest;
import ilog.rules.res.session.IlrSessionResponse;
import ilog.rules.res.model.IlrPath;

import javax.ws.rs.*;
import javax.ws.rs.core.MediaType;

/**
 * IBM ODM HTDS REST endpoint.
 *
 * This is what the Python agent calls via HTTP POST /api/authorize.
 * Deployed on IBM Rule Execution Server (WebSphere / Liberty).
 *
 * The ruleflow "PaymentAuthorizationFlow" runs 5 rules sequentially:
 *   1. AmountLimitRule
 *   2. CountryBlacklistRule
 *   3. MCCRestrictionRule
 *   4. CardValidityRule
 *   5. ContactlessLimitRule
 *
 * Rules are authored in BAL inside Decision Center and deployed as a RuleApp.
 */
@Path("/api/authorize")
@Produces(MediaType.APPLICATION_JSON)
@Consumes(MediaType.APPLICATION_JSON)
public class PaymentAuthorizationResource {

    // RuleApp path — matches the deployment in Decision Center
    private static final String RULEAPP_PATH =
        "/PaymentAuthorizationRuleApp/1.0/PaymentAuthorizationRuleset/1.0";

    @POST
    public AuthorizationResponse authorize(TransactionRequest request) {
        try {
            IlrJ2SESessionFactory factory = new IlrJ2SESessionFactory();
            IlrStatelessSession session = factory.createStatelessSession();

            IlrSessionRequest sessionRequest = factory.createRequest();
            sessionRequest.setRulesetPath(IlrPath.parsePath(RULEAPP_PATH));

            // Input objects bound to the ruleflow's input parameters
            sessionRequest.setInputParameter("transaction", request);

            AuthorizationResponse response = new AuthorizationResponse();
            sessionRequest.setInputParameter("response", response);

            // Execute ruleflow — all 5 rules fire sequentially
            IlrSessionResponse sessionResponse = session.execute(sessionRequest);

            // Output parameters populated by the rules
            return (AuthorizationResponse) sessionResponse.getOutputParameters().get("response");

        } catch (Exception e) {
            AuthorizationResponse errorResponse = new AuthorizationResponse();
            errorResponse.setDecision("ERROR");
            errorResponse.setResponseCode("96");   // ISO 8583 — System malfunction
            errorResponse.setDeclineReason("Rule engine error: " + e.getMessage());
            return errorResponse;
        }
    }

    @GET
    @Path("/health")
    public String health() {
        return "{\"status\": \"ok\", \"engine\": \"IBM ODM RES\"}";
    }
}
