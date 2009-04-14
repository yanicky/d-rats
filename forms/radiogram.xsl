<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform" version="1.0">
    <xsl:output method="html"/>

    <xsl:template match="form">
      <html>
	<head>
	  <style type="text/css">
	    td.field {
   	       border: none;
	       border-spacing: 0px;
	    }

	    .form {
	      width: 90%;
	      border-spacing: 0px;
	      border-collapse: collapse;
	      padding: 0px;
	    }

	    .group {
	       border-spacing: 0px;
	       border-collapse: collapse;
	       border: 1px solid black
	    }

	    .line {
	       width: 100%;
	    }

	    .title {
	       text-align: center;
	    }

	    table {
	       border-collapse: collapse;
 	       padding: 0px;
	    }

	    .field-caption {
	       font-size: 60%;
	       font-weight: bold;
	    }

	    .field-content {
	       font-family: Arial, Helvetica, sans-serif;
	       white-space: pre;
	    }

	  </style>
	</head>
	<body>
	  
	  <h1 class="title">
	    <xsl:value-of select="title"/>
	  </h1>

	  <table class="form">

	    <table class="line">
	      <tr>
		<td class="group">
		  <xsl:apply-templates select="field[@id='number']"/>
		</td>
		<td class="group">
		  <xsl:apply-templates select="field[@id='precedence']"/>
		</td>
		<td class="group">
		  <xsl:apply-templates select="field[@id='hx']"/>
		</td>
		<td class="group">
		  <xsl:apply-templates select="field[@id='station']"/>
		</td>
		<td class="group">
		  <xsl:apply-templates select="field[@id='_auto_check']"/>
		</td>
		<td class="group">
		  <xsl:apply-templates select="field[@id='place']"/>
		</td>
		<td class="group">
		  <xsl:apply-templates select="field[@id='time']"/>
		</td>
		<td class="group">
		  <xsl:apply-templates select="field[@id='date']"/>
		</td>
	      </tr>
	    </table>

	    <div class="line">
	      <div class="group">
		<table>
		  <tr><td>
		      <xsl:apply-templates select="field[@id='recip']"/>
		  </td></tr><tr><td>
		      <xsl:apply-templates select="field[@id='recip_phone']"/>
		  </td></tr>
		</table>
	      </div>
	    </div>

	  <table class="line">
	    <xsl:apply-templates select="field[@id='_auto_message']"/>
	  </table>

	  <br/>

	  <table class="line">
	    <tr class="group">
	      <td colspan="2">
		<xsl:apply-templates select="field[@id='sig']"/>
	      </td>
	    </tr>
	    <tr class="group">
	      <td>
		<xsl:apply-templates select="field[@id='received']"/>
	      </td><td>
		<xsl:apply-templates select="field[@id='received_from']"/>
	      </td><td>
		<xsl:call-template name="_field">
		  <xsl:with-param name="caption">
		    <xsl:text>Date / Time</xsl:text>
		  </xsl:with-param>
		  <xsl:with-param name="value">
		    <xsl:value-of select="field[@id='recv_t']/entry"/>
		    <xsl:text> </xsl:text>
		    <xsl:value-of select="field[@id='recv_d']/entry"/>
		  </xsl:with-param>
		</xsl:call-template>
	      </td>
	    </tr>
	    <tr class="group">
	      <td>
		<xsl:apply-templates select="field[@id='sent']"/>
	      </td><td>
		<xsl:apply-templates select="field[@id='sent_to']"/>
	      </td><td>
		<xsl:call-template name="_field">
		  <xsl:with-param name="caption">
		    <xsl:text>Date / Time</xsl:text>
		  </xsl:with-param>
		  <xsl:with-param name="value">
		    <xsl:value-of select="field[@id='sent_t']/entry"/>
		    <xsl:text> </xsl:text>
		    <xsl:value-of select="field[@id='sent_d']/entry"/>
		  </xsl:with-param>
		</xsl:call-template>
	      </td>
	    </tr>
	  </table>
	  </table>
	</body>
      </html>
    </xsl:template>

    <xsl:template match="entry">
      <xsl:choose>
	<xsl:when test="@type='choice'">
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
