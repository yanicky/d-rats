<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform" version="1.0">
    <xsl:output method="html"/>

    <xsl:template match="form">
      <html>
	<head>
	  <style type="text/css">
	    
	    div.field {
	       border: 1px solid black;
	    }

	    td.field {
   	       border: none;
	    }

	    .title {
	       text-align: center;
	    }

	    .line {
	       width: 100%;
	    }

	    .group {
	       border-spacing: 0px;
	       border-collapse: collapse;
	       border: 1px solid black
	    }

	    table {
	       border-collapse: collapse;
	    }

	    .form {
	       width: 80%;
	       border-spacing: 0px;
	       border-collapse: collapse;
	       padding-top: 0px;
	       padding-bottom: 0px;
	    }

	    .field-caption {
	       font-size: 60%;
	       font-weight: bold;
	    }

	    .field-content {
	       font-family: Arial, Helvetica, sans-serif;
	       white-space: pre;
	    }

	    .fineprint {
	       font-size:40%;
	    }

	  </style>
	</head>
	<body>
	  <h1 class="title">
	    <xsl:value-of select="title"/>
	  </h1>
	  
	  <table class="form" cellpadding="0" align="center">
	    <tr><td>

		<table class="line" cellspacing="0" cellpadding="0">
		  <tr>
		    <td class="group">
		      <xsl:apply-templates select="field[@id='incident']"/>
		    </td>
		    <td class="group">
		      <xsl:call-template name="_field">
			<xsl:with-param name="caption">
			  <xsl:text>Date/Time of message</xsl:text>
			</xsl:with-param>
			<xsl:with-param name="value">
			  <xsl:value-of select="field[@id='date']/entry"/>
			  <xsl:text> </xsl:text>
			  <xsl:value-of select="field[@id='time']/entry"/>
			</xsl:with-param>
		      </xsl:call-template>
		    </td>
		    <td class="group">
		      <div align="right">
			<b>GENERAL MESSAGE</b><br/>
			<b>ICS 213-OS</b>
		      </div>
		    </td>
		  </tr>
		</table>

	    </td></tr><tr><td>

		<table class="line">
		  <tr class="group">
		    <td>
		      <xsl:apply-templates select="field[@id='recip']"/>
		    </td><td>
		      <xsl:apply-templates select="field[@id='to_pos']"/>
		    </td>
		  </tr>
		  <tr class="group">
		    <td>
		      <xsl:apply-templates select="field[@id='sender']"/>
		      </td><td>
		      <xsl:apply-templates select="field[@id='from_pos']"/>
		    </td>
		  </tr>
		</table>

	    </td></tr>
	    <tr><td>

		<table class="line">
		  <tr class="line">
		    <td class="group">
		      <xsl:apply-templates select="field[@id='subject']"/>
		    </td>
		  </tr>
		  <tr class="line">
		    <td class="group">
		      <xsl:apply-templates select="field[@id='message']"/>
		    </td>
		  </tr>
		  <tr class="line">
		    <td class="group">
		      <xsl:apply-templates select="field[@id='reply']"/>
		    </td>
		  </tr>
		</table>
		
	    </td></tr>
	    <tr><td>
		
		<table class="line">
		  <tr class="group">
		    <td>
		      <xsl:apply-templates select="field[@id='sig']"/>
		    </td><td>
		      <xsl:call-template name="_field">
			<xsl:with-param name="caption">
			  <xsl:text>Date/Time of reply</xsl:text>
			</xsl:with-param>
			<xsl:with-param name="value">
			  <xsl:value-of select="field[@id='date_reply']/entry"/>
			  <xsl:text> </xsl:text>
			  <xsl:value-of select="field[@id='time_reply']/entry"/>
			</xsl:with-param>
		      </xsl:call-template>
		    </td>
		  </tr>
		</table>
		
	    </td></tr>
	    <tr><td>
		<table class="line">
		  <tr class="group">
		    <td width="33%">GENERAL MESSAGE</td>
		    <td width="33%" align="center"><small>June 2000</small></td>
		    <td width="33%" align="right">ICS213-OS</td>
		  </tr>
		</table>
	    </td></tr>
	  </table>
	  <div align="right" class="form">
	    <span class="fineprint">
	      Electronic version: Generated by D-RATS
	    </span>
	  </div>

	</body>
      </html>
    </xsl:template>

    <xsl:template match="entry">
      <xsl:choose>
	<xsl:when test="@type = 'choice'">
	  <xsl:value-of select="choice[@set='y']"/>
	</xsl:when>
	<xsl:otherwise>
	  <xsl:value-of select="."/>
	</xsl:otherwise>
      </xsl:choose>
    </xsl:template>

    <xsl:template name="_field">
      <xsl:param name="caption"/>
      <xsl:param name="value"/>
      <table class="element">
	<tr>
	  <td class="field">
	    <span class="field-caption">
	      <xsl:value-of select="$caption"/>
	    </span>
	  </td>
	</tr><tr>
	  <td>
	    <span class="field-content">
	      <xsl:value-of select="$value"/>
	    </span>
	  </td>
	</tr>
      </table>
    </xsl:template>

    <xsl:template match="field">
      <xsl:call-template name="_field">
	<xsl:with-param name="caption" select="caption"/>
	<xsl:with-param name="value">
	  <xsl:apply-templates select="entry"/>
	</xsl:with-param>
      </xsl:call-template>
    </xsl:template>

</xsl:stylesheet>
