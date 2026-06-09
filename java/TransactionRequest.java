package com.bank.odm.model;

/**
 * BOM (Business Object Model) class — the rule vocabulary exposed in Decision Center.
 * This is the input to the ruleflow; BAL rules reference fields by their property names.
 */
public class TransactionRequest {

    private double transactionAmount;
    private String cardNumber;
    private String merchantId;
    private String mcc;          // ISO 18245 Merchant Category Code
    private String country;      // ISO 3166-1 alpha-2
    private String entryMode;    // CHIP | NFC_CONTACTLESS | SWIPE | MANUAL
    private String currency;     // ISO 4217

    public TransactionRequest() {}

    public double getTransactionAmount() { return transactionAmount; }
    public void setTransactionAmount(double transactionAmount) { this.transactionAmount = transactionAmount; }

    public String getCardNumber() { return cardNumber; }
    public void setCardNumber(String cardNumber) { this.cardNumber = cardNumber; }

    public String getMerchantId() { return merchantId; }
    public void setMerchantId(String merchantId) { this.merchantId = merchantId; }

    public String getMcc() { return mcc; }
    public void setMcc(String mcc) { this.mcc = mcc; }

    public String getCountry() { return country; }
    public void setCountry(String country) { this.country = country; }

    public String getEntryMode() { return entryMode; }
    public void setEntryMode(String entryMode) { this.entryMode = entryMode; }

    public String getCurrency() { return currency; }
    public void setCurrency(String currency) { this.currency = currency; }
}
